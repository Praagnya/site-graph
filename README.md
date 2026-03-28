# Site Graph Mapper

An AI agent that autonomously explores web applications and produces a **state graph** — a directed graph where each node is a distinct visual/interactive state and each edge is the action taken to transition between states.

Works on both server-rendered sites and modern SPAs where traditional crawlers (following `<a href>` links) break down.

---

## How it works

```
Observe → Fingerprint → Record → Decide → Act → Guard → repeat
```

1. **Observe** — extracts visible interactive elements from the live DOM (buttons, links, inputs, selects)
2. **Fingerprint** — SHA-256 hash of `(url + element tags/texts)` identifies each unique state, not just the URL
3. **Record** — adds a node to the graph if the state is new, adds an edge from the previous state
4. **Decide** — GPT-4o picks the next action given the elements, history, and visited URLs
5. **Act** — Playwright executes the action (`click`, `fill`, `press`)
6. **Guard** — detects off-domain navigation, goes back, and blocks that element going forward

---

## Features

- **SPA-aware state identity** — same URL with different content (modal open, logged in vs out) correctly maps to different nodes
- **Structured LLM output** — GPT-4o returns a typed `Action` via Pydantic, no free-text parsing
- **Credential injection** — pass `--username` / `--password` for sites that require login
- **Link deduplication** — collapses `/author/*`, `/tag/*` floods while preserving pagination (`/page/1/`, `/page/2/`)
- **Auto-termination** — hard step cap + LLM can self-terminate when exploration is complete
- **Per-run logging** — timestamped directories with screenshots per step and a full run log

---

## Output

```json
{
  "nodes": [
    {
      "id": "state_001",
      "url": "https://example.com/",
      "title": "Home",
      "dom_fingerprint": "a3f8c1...",
      "interactive_elements": ["el_0", "el_1", "el_2"],
      "screenshot": "logs/run_dir/step_01.png"
    }
  ],
  "edges": [
    {
      "from": "state_001",
      "to": "state_002",
      "action": {
        "type": "click",
        "target": "el_1",
        "description": "Clicked the Login link"
      }
    }
  ]
}
```

---

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file:
```
OPENAI_API_KEY=sk-...
```

---

## Usage

```bash
# Basic
python agent.py https://example.com

# With credentials
python agent.py https://example.com --username admin --password secret

# Custom step limit
python agent.py https://example.com --max-steps 25
```

Results are saved to `logs/<timestamp>_<domain>/`:
- `graph_output.json` — the full state graph
- `step_01.png`, `step_02.png`, ... — screenshots per step
- `run.log` — full debug log

---

## Architecture

| File | Responsibility |
|---|---|
| `agent.py` | Main run loop, orchestration, logging |
| `browser.py` | Playwright: navigate, extract elements, execute actions |
| `llm.py` | GPT-4o prompt construction and structured response parsing |
| `state_tracker.py` | SHA-256 fingerprinting, graph nodes/edges, deduplication |

See [`design.md`](design.md) for full architecture notes and tradeoff discussion.

---

## Tested on

| Site | Type | States found |
|---|---|---|
| `quotes.toscrape.com` | Server-rendered | 6 |
| `demo.playwright.dev/todomvc` | React SPA | 6 |
| `excalidraw.com` | React SPA | 5 |
