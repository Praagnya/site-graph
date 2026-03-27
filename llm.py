import logging
from typing import Optional
from openai import OpenAI
from pydantic import BaseModel
from state_tracker import Action


class _LLMResponse(BaseModel):
    """Raw OpenAI structured output — field names match Action but no alias complexity."""
    type: str
    target: Optional[str] = None
    value: Optional[str] = None
    key: Optional[str] = None
    description: str


def ask_llm(
    client: OpenAI,
    url: str,
    elements: list,
    history: list,
    visited_urls: list,
    blocked_targets: list,
    log: logging.Logger,
    credentials: dict | None = None,
) -> Action:
    system_prompt = (
        "You are an AI web exploration agent. Your goal is to systematically map all distinct "
        "states of a web application by interacting with it.\n\n"
        "Priority order for choosing the next action:\n"
        "  1. Actions likely to reveal a completely new URL not in 'Already visited URLs'.\n"
        "  2. Actions likely to reveal a new UI state on the current page (open a modal, expand a section, switch a tab).\n"
        "  3. Actions on elements not yet tried on this page.\n"
        "  4. Return type='finish' only when all elements have been tried and no new states are reachable.\n\n"
        "Rules:\n"
        "  - Never interact with elements listed under 'Blocked targets'.\n"
        "  - Avoid repeating an action (same type + same target) already in the recent history.\n"
        "  - For a login/signup form: fill ALL text and password inputs first, then click submit.\n"
        "  - When credentials are provided, use them exactly — do not invent alternatives.\n"
        "  - input[type=submit] and input[type=button] must use 'click', never 'fill'.\n"
        "  - Deprioritize destructive actions (logout, delete, 'clear all', 'remove') — explore them last.\n"
        "  - After filling a text input with no visible submit button, use 'press' with key='Enter'.\n\n"
        "Action types:\n"
        "  - 'click'  : click an element (provide target)\n"
        "  - 'fill'   : type into a text/password input (provide target and value)\n"
        "  - 'press'  : press a key on an element (provide target and key, e.g. 'Enter')\n"
        "  - 'finish' : all meaningful interactions exhausted — end exploration\n"
    )

    elements_text = "\n".join(
        f"  {el['id']} | <{el['tag']}> type={el.get('type','')!r} | {el['text']!r}"
        for el in elements
    )

    history_text = "\n".join(
        f"  {i+1}. {a['type']} on {a.get('target', '-')} — {a.get('description', '')[:60]}"
        for i, a in enumerate(history[-5:])
    ) or "  (none yet)"

    visited_text = "\n".join(f"  - {u}" for u in visited_urls) or "  (none yet)"
    blocked_text = "\n".join(f"  - {t}" for t in blocked_targets) or "  (none)"
    creds_text = (
        f"  username: {credentials['username']}\n  password: {credentials['password']}"
        if credentials else "  (none provided — do not attempt login)"
    )

    user_prompt = (
        f"Current URL: {url}\n\n"
        f"Interactive elements:\n{elements_text}\n\n"
        f"Already visited URLs:\n{visited_text}\n\n"
        f"Recent actions:\n{history_text}\n\n"
        f"Blocked targets (do NOT interact with these):\n{blocked_text}\n\n"
        f"Credentials:\n{creds_text}\n\n"
        "What is the single best next action to discover a new state?"
    )

    log.debug("Calling LLM ...")
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        response_format=_LLMResponse,
        temperature=0.2,
    )

    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("LLM returned an unparseable response")
    # Map LLM field names to our Action model
    return Action(
        type=parsed.type,
        target=parsed.target,
        value=parsed.value,
        key=parsed.key,
        description=parsed.description,
    )
