# Site Graph Mapper — Design Document

## Architecture

The agent is a synchronous Python loop using Playwright for browser automation and OpenAI GPT-4o for decision-making. It is split into four focused modules:

| File | Responsibility |
|---|---|
| `agent.py` | Main run loop, orchestration, logging |
| `browser.py` | Playwright: navigate, extract elements, execute actions |
| `llm.py` | OpenAI prompt construction and structured response parsing |
| `state_tracker.py` | SHA-256 fingerprinting, graph nodes/edges, deduplication |

**Where the LLM fits vs deterministic code:**
- **Deterministic:** element extraction, fingerprinting, graph bookkeeping, domain guard, loop termination
- **LLM:** deciding *which* element to interact with next — the only step that requires reasoning about semantics

### Core Loop

```
for each step (up to MAX_STEPS):
    1. Observe       → extract visible interactive elements, take screenshot
    2. Fingerprint   → SHA-256 hash of (url + element tags/texts)
    3. Record        → add node if new, add edge from previous state
    4. Decide        → ask LLM for next action given elements + history
    5. Act           → execute action via Playwright (click / fill / press)
    6. Guard         → if navigated off-domain, go back and block that target
```

Stops when the LLM returns `action.type == "finish"` or the step limit is reached.

---

## Page Representation

Raw HTML is not sent to the LLM — it is too large, noisy, and hallucination-prone. Instead the agent sends a structured extraction:

- **URL + page title** — page-level context
- **Interactive elements list** — extracted via `page.evaluate()` in the browser:
  - Selector: `button, a, input, textarea, select, [role="button"], [role="link"]`
  - Filtered: hidden elements (`display:none`, `visibility:hidden`) and `disabled` elements excluded
  - Deduplicated: links sharing the same first path segment (e.g. `/tag/*`, `/author/*`) are collapsed to one representative — avoids flooding the LLM with 20 identical tag links
  - Each element stamped with `data-ai-id="el_N"` directly on the DOM node — gives Playwright an unambiguous, stable selector regardless of how many identical tags exist on the page
  - For `input`/`textarea`, text is taken from `placeholder` (not `value`) so filling a field does not change the fingerprint
- **Recent action history** — last 5 actions passed to the LLM to discourage re-doing the same flow
- **Visited URLs** — full list of URLs seen, so the LLM can prioritise unexplored paths
- **Blocked targets** — element IDs that triggered off-domain navigation, explicitly excluded from future actions

---

## State Identity

A state is defined by its **URL + DOM fingerprint**, not URL alone. This correctly handles:

- **SPAs** — same URL, different content (e.g. modal open = different fingerprint)
- **Auth state** — logged-out home vs logged-in home share the same URL but different elements (e.g. Login vs Logout button) → different fingerprints → different nodes
- **Pagination** — `/page/1/` vs `/page/2/` are different URLs → always different nodes

**Fingerprint algorithm:**
```python
simplified = [{"tag": el["tag"], "text": el["text"]} for el in elements]
sha256(json.dumps({"url": url, "elements": simplified}, sort_keys=True))
```

Input values are intentionally excluded from the fingerprint — filling a form field does not create a new state.

**Known limitation:** Two pages with structurally identical elements but different data (e.g. a different user's profile page at the same URL pattern) will hash to the same fingerprint and be treated as one state. For a site-mapping use case that is acceptable.

---

## LLM Integration

The LLM is used for a single, well-scoped task: **choosing the next action** given the current page context. It is not asked to interpret raw HTML, generate code, or make open-ended judgements.

### Structured Output

The call uses OpenAI's `response_format` with a Pydantic model (`_LLMResponse`) and `client.beta.chat.completions.parse()`. This enforces a strict JSON schema — the model cannot return a malformed action or hallucinate extra fields:

```python
class _LLMResponse(BaseModel):
    type: str           # one of: click | fill | press | finish
    target: Optional[str]
    value: Optional[str]
    key: Optional[str]
    description: str
```

`temperature=0.2` is used for low variance — the agent should make consistent, deterministic choices, not creative ones.

### Prompt Design

The system prompt defines explicit rules:
- Prefer actions leading to NEW states (new URLs, modals, forms)
- Never re-use elements listed in `blocked_targets`
- Fill all text inputs before clicking submit
- `input[type=submit]` uses `click`, never `fill`
- Return `finish` when exploration is complete

The user prompt injects four context blocks:
1. Current URL
2. Interactive elements (id, tag, type, text)
3. Already-visited URLs
4. Recent action history (last 5 steps)

This keeps the prompt minimal and factual — the LLM reasons over a structured element list rather than a 50 kB HTML dump.

### Parse Failure Handling

```python
if parsed is None:
    raise ValueError("LLM returned an unparseable response")
```

The agent crashes loudly rather than silently proceeding with a `None` action. In production this would be caught and retried; for the prototype, an explicit failure is more debuggable.

---

## Exploration Strategy

**What to interact with next:** The LLM receives the full element list plus history and visited URLs. It is prompted to prefer actions that lead to new states and avoid repeating known paths. The LLM also understands action semantics — e.g. fill text inputs before clicking submit, use `press Enter` when there is no submit button.

**Avoiding infinite loops:** Three mechanisms work together:
1. The state tracker detects revisits by fingerprint — `(REVISIT)` is logged and the LLM is informed of already-visited URLs
2. Action history (last 5 steps) is included in every LLM prompt
3. Duplicate edges (same `from → to` via same element) are silently skipped

**Off-domain navigation:** After every action, the agent checks whether the domain changed. If it did, it navigates back and adds the triggering element to a `blocked_targets` list that is passed to the LLM going forward.

**Disabled elements:** Filtered out at extraction time so the LLM never attempts to interact with them.

**Modal overlays:** When a modal is open, background elements are visible in the DOM but pointer-blocked. The agent logs a warning and moves on. A future improvement would be to press `Escape` to dismiss overlays before re-exploring.

**Stopping:** Hard cap at `MAX_STEPS = 15`. The LLM can also self-terminate with `action.type == "finish"` when it believes exploration is complete.

---

## Error Handling

| Failure mode | Handling |
|---|---|
| `networkidle` timeout on navigate | Falls back to `wait_for_load_state("load")` — prevents hanging on apps that never go fully idle |
| `networkidle` timeout post-action | Same fallback — ensures the loop always continues |
| Playwright action fails (element gone, pointer-blocked, timeout) | `try/except` logs a warning and returns `True` — exploration continues to the next step |
| LLM returns `None` (parse failure) | `ValueError` raised immediately — fails loudly rather than silently skipping |
| Off-domain navigation | Domain check after every action; `go_back()` + target added to `blocked_targets` |
| Step limit exceeded | `MAX_STEPS = 15` hard cap — guarantees bounded cost and termination |

The design principle is **fail loudly on LLM errors** (programmer errors, prompt bugs) and **fail gracefully on browser errors** (the web is unpredictable; one blocked click should not abort the run).

---

## Action Types

| Type | Description | Required fields |
|---|---|---|
| `click` | Click a button, link, or interactive element | `target` |
| `fill` | Type text into an input or textarea | `target`, `value` |
| `press` | Press a keyboard key on an element (e.g. Enter to submit) | `target`, `key` |
| `finish` | LLM signals exploration is complete | — |

All actions use `[data-ai-id="el_N"]` as the Playwright selector — injected during extraction, unique per page observation.

---

## Graph Model

### Node
```json
{
  "id": "state_001",
  "url": "https://example.com/dashboard",
  "title": "Dashboard — Overview",
  "dom_fingerprint": "a3f8c1...",
  "interactive_elements": ["el_0", "el_1", "el_2"],
  "screenshot": "logs/run_dir/step_01.png"
}
```

### Edge
```json
{
  "from": "state_001",
  "to": "state_002",
  "action": {
    "type": "click",
    "target": "el_1",
    "value": null,
    "key": null,
    "description": "Clicked the Login link to explore the auth flow"
  }
}
```

---

## Design Tradeoffs

| Decision | Why | Cost |
|---|---|---|
| Structured element extraction vs raw HTML | ~10× token reduction; focused context; less hallucination surface | Canvas/SVG/custom-rendered elements are invisible |
| Synchronous single-tab loop vs async multi-tab | Simpler control flow; no race conditions between parallel navigations | Slower exploration; acceptable for design mapping |
| SHA-256 (URL + elements) for state identity vs URL-only | Correctly handles SPAs, modals, auth state changes | Structurally identical pages (e.g. two different user profiles) are collapsed to one node |
| LLM chooses next action vs BFS/DFS | Understands semantics (fill before submit, avoid nav links when exploring a modal) | Non-deterministic; mitigated by low temperature + history window |
| Hard step cap (MAX_STEPS = 15) | Guarantees bounded API cost and runtime | May miss deeply-nested states on large apps; configurable via CLI |

---

## Tested Sites

| Site | Type | States | Notes |
|---|---|---|---|
| `quotes.toscrape.com` | Server-rendered | 5–6 | Login flow, pagination, author pages |
| `demo.playwright.dev/todomvc` | React SPA | 6 | Hash routing, keyboard Enter to submit |
| `todomvc.com/examples/react` | React SPA | 6 | Same app, consistent results |
| `excalidraw.com` | React SPA | 5 | Modal overlays block some clicks (expected) |

---

## Known Limitations & Future Work

- **Modal overlay blocking** — elements behind open modals are pointer-blocked. Fix: press `Escape` before re-exploring when stuck.
- **Hover-only elements** — elements only visible on hover (e.g. todo delete button) are in the DOM but not interactable without a hover action. Fix: add a `hover` action type.
- **LLM history window** — only the last 5 actions are sent. Long flows (e.g. multi-step forms) can fall out of context, causing the LLM to repeat them. Fix: track completed state transitions explicitly and pass them as a summary.
- **External links** — blocked by domain guard, but consume one LLM context slot. Future: exclude them at extraction time if `href` is absolute and off-domain.
- **LLM parse failure recovery** — currently raises immediately. Production hardening: retry up to N times with a simplified prompt before aborting.
