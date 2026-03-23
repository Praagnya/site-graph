SDE Interview: AI Web Agent
Interactive Site Graph Mapper
Background
Traditional web crawlers discover pages by following <a href> links in HTML. This works for static, server-rendered sites but completely breaks down for modern single-page applications (SPAs) where navigation happens via JavaScript, content loads dynamically, and important UI states — modals, drawers, dropdowns, multi-step forms — are invisible in the raw HTML.

Your task is to design and build a prototype AI agent that can autonomously explore a web application and produce a state graph: a directed graph where each node represents a distinct visual/interactive state of the application, and each edge represents the action taken to transition between states.

Requirements
The agent should be able to:
Start from a given URL
Log in with provided credentials if authentication is required
Discover and interact with UI elements (buttons, links, forms, tabs, modals, etc.)
Recognize when it has reached a new "state" vs. revisiting an existing one
Output a structured graph of the discovered states and transitions

Environment
Node.js / Python (your choice)
Playwright installed
Access to an LLM API (OpenAI or Anthropic)
A target test application to explore

Deliverables
1. Design Document
Before you start coding, write a brief design doc (can be a markdown file, comments at the top of your code, or a separate document) that covers:

Architecture: How is the agent structured? What does the core loop look like? Where does the LLM fit in vs. deterministic code?
Page Representation: How do you feed the current page context to the LLM? (raw HTML, accessibility tree, screenshot, structured extraction, or a combination?)
State Identity: How do you determine whether the agent is looking at a "new" state or one it has already visited? Consider cases like the same URL with different content, visually similar pages with different data, or minor UI differences.
Exploration Strategy: How does the agent decide what to interact with next? How do you avoid infinite loops or revisiting the same states? How do you handle potentially destructive actions (delete, logout)? How do you know when exploration is "done"?
Graph Model: What does a node contain? What does an edge contain?

2. Working Prototype
Build a minimal working version of the agent that:
Opens a browser to the target URL
Uses the LLM to identify interactive elements and decide what action to take
Tracks at least 3–5 distinct states
Outputs a JSON graph with nodes and edges

You do not need to handle destructive action avoidance in the prototype. Focus on getting a clean observe → decide → act → record loop working with reliable state tracking.

Example Output Structure
{
  "nodes": [
    {
      "id": "state_001",
      "url": "https://example.com/dashboard",
      "title": "Dashboard — Overview",
      "dom_fingerprint": "a3f8c1...",
      "interactive_elements": ["nav-link-settings", "btn-create-new"],
      "screenshot": "screenshots/state_001.png"
    }
  ],
  "edges": [
    {
      "from": "state_001",
      "to": "state_002",
      "action": {
        "type": "click",
        "target": "nav-link-settings",
        "description": "Clicked 'Settings' in the left nav"
      }
    }
  ]
}

Time
You have 2 hours to complete both deliverables. We recommend spending roughly 20 minutes on design and the rest on implementation. It's fine if the prototype doesn't cover every edge case — we care more about a well-structured approach than exhaustive coverage.

Evaluation Criteria
Design thinking: Is the architecture clear? Are tradeoffs acknowledged?
State modeling: Does the approach handle SPAs, dynamic content, and same-URL-different-state scenarios thoughtfully?
LLM integration: Is the LLM used effectively with structured prompts and clear action definitions, rather than vague open-ended queries?
Code quality: Is the code modular, readable, and well-structured?
Error handling: Does the agent handle unexpected situations gracefully (timeouts, missing elements, LLM parse failures)?
Communication: Is the design doc clear enough that another engineer could understand and extend the work?
