# Site Graph Mapper - Design Document

## Architecture
The agent is structured as a synchronous Python loop using Playwright for browser automation and OpenAI's API for decision-making.

### Core Loop
1. **Observe**: Extract the current page state (URL, title, screenshot, and a list of interactive elements).
2. **Identify State**: Compute a fingerprint of the current state. Check if it's a new node or previously visited. Ensure the new node/edge is recorded in our Graph.
3. **Decide Action**: Feed the current state context to the LLM. The LLM returns an action (e.g., click an element, fill a form, or finish exploration).
4. **Act**: Execute the action via Playwright.
5. **Repeat**: Go back to step 1, stopping when the LLM decides no more unexplored actions are needed or a max step limit is reached.

### Component Breakdown
- `BrowserController`: Wraps Playwright to launch the browser, navigate, extract DOM context, take screenshots, and execute actions on elements.
- `StateTracker`: Maintains the directed graph (Nodes and Edges). Computes state fingerprints to determine equivalence.
- `LLMAgent`: Prompts the OpenAI API with current state context and gets a structured JSON response predicting the next action.
- `Main Loop`: Orchestrates the interaction between the above components.

## Page Representation
The LLM will not receive the full raw HTML as it's often too large and noisy (exceeding context limits, hallucination risk). Instead, we feed the LLM a structured extraction:
- **Page Metadata**: URL, Page Title.
- **Interactive Elements List**: We execute a script in the browser to find all visible, interactive elements (`<a>`, `<button>`, `<input>`, `[role="button"]`, etc.). We assign a unique numeric ID (e.g., `elem-1`) to each element for this state, along with its text content, attributes (href, placeholder), and type.
- **Previous Actions**: A short history of what the agent has done so far to provide context and prevent looping.

## State Identity
A state is defined not just by the URL, but by the available interactive elements. For SPAs, a modal opening is a new state.
- **`dom_fingerprint`**: We construct a normalized string representing all visible interactive elements (their tag name, text content, and structural role). We hash this string (e.g., using SHA-256).
- If two states share the exact same URL and the same `dom_fingerprint`, they are considered the same node. Minor dynamic data differences are ignored because we only hash the structure and labels of interactive elements.

## Exploration Strategy
- **Deciding what to interact with next**: The LLM is given the list of elements and told to explore systematically. We provide it with the list of actions it has already taken in the current state to encourage trying new things.
- **Avoiding infinite loops/Revisiting**: The state tracker maintains a history of edges `(State_A -> State_B via Element X)`. If the LLM proposes an action that we know leads back to an already fully-explored state, we can reprompt or inform it.
- **Stopping**: We cap the exploration to a maximum number of steps (e.g., 20). The LLM can also return a 'finish' action if it believes the core flows have been mapped.

## Graph Model
- **Node**: 
  - `id`: Unique state ID (e.g., `state_1`).
  - `url`: The URL of the page.
  - `title`: The `<title>` of the page.
  - `dom_fingerprint`: Hash used for equivalence checking.
  - `interactive_elements`: A list of the parsed elements available on this page.
  - `screenshot`: Path to the screenshot file for this state.
- **Edge**:
  - `from`: Origin Node ID.
  - `to`: Destination Node ID.
  - `action`: The action taken (e.g., `click` on element `elem-1`).
