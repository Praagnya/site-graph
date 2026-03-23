import os
import json
import time
from dotenv import load_dotenv
from typing import List, Optional
from pydantic import BaseModel
from openai import OpenAI
from playwright.sync_api import sync_playwright, Page
from state_tracker import GraphTracker, Action

load_dotenv()

class LLMActionResponse(BaseModel):
    action_type: str  # "click", "fill", "finish"
    target_id: Optional[str] = None
    value: Optional[str] = None
    reasoning: str

EXTRACT_JS = """
() => {
    let elements = [];
    let counter = 0;
    const interactables = document.querySelectorAll('a, button, input, textarea, select, [role="button"], [role="link"]');
    for (let el of interactables) {
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || el.offsetWidth === 0 || el.offsetHeight === 0) continue;
        
        let id = "elem-" + counter++;
        // Annotate the DOM so Playwright can click it easily
        el.setAttribute('data-ai-id', id);
        
        elements.push({
            "tag": el.tagName,
            "text": el.innerText || el.value || '',
            "role": el.getAttribute('role') || '',
            "href": el.getAttribute('href') || ''
        });
        // We add the id afterwards to match our pydantic requirement but keep it clean
        elements[elements.length - 1]["id"] = id;
    }
    return {
        url: window.location.href,
        title: document.title,
        elements: elements
    };
}
"""

class BrowserController:
    def __init__(self, page: Page):
        self.page = page

    def observe(self):
        self.page.wait_for_load_state("networkidle")
        time.sleep(1) # Extra buffer for SPAs
        data = self.page.evaluate(EXTRACT_JS)
        return data

    def execute_action(self, action: Action):
        if action.type == "finish":
            return
        
        target = f"[data-ai-id='{action.target}']"
        try:
            if action.type == "click":
                self.page.click(target, timeout=5000)
            elif action.type == "fill":
                self.page.fill(target, action.value or "", timeout=5000)
        except Exception as e:
            print(f"Action failed: {e}")

class Agent:
    def __init__(self, page: Page):
        self.controller = BrowserController(page)
        self.tracker = GraphTracker()
        self.openai_client = OpenAI()
        os.makedirs("screenshots", exist_ok=True)

    def ask_llm(self, current_url: str, elements: list, history: list) -> Action:
        system_prompt = (
            "You are an AI Web Exploration Agent. Your goal is to systematically explore a web application "
            "and map its distinct states. Return a JSON describing the next action to take.\n"
            "Action types allowed: 'click', 'fill', 'finish'.\n"
            "Provide the 'target_id' of the element to interact with, and a 'value' if filling text.\n"
            "If you believe all relevant states are explored, return type 'finish'.\n"
            "Ensure you return a valid JSON matching the schema: { 'action_type': str, 'target_id': str|null, 'value': str|null, 'reasoning': str }"
        )
        
        user_prompt = f"Current URL: {current_url}\n\n"
        user_prompt += "Interactive Elements:\n"
        for el in elements:
            user_prompt += f"- ID: {el['id']} | TAG: {el['tag']} | TEXT: {el['text']} | HREF: {el['href']}\n"
        
        user_prompt += "\nRecent Actions History:\n"
        for act in history[-5:]:
            user_prompt += f"- {act.type} on {act.target}\n"
            
        user_prompt += "\nDecide your next action carefully to avoid repeating paths unless necessary."

        response = self.openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format=LLMActionResponse,
            temperature=0.2
        )
        
        decision = response.choices[0].message.parsed
        return Action(
            type=decision.action_type,
            target=decision.target_id,
            value=decision.value,
            description=decision.reasoning
        )

    def run(self, start_url: str, max_steps: int = 10):
        self.controller.page.goto(start_url)
        actions_history = []
        current_node_id = None
        
        for step in range(max_steps):
            print(f"--- Step {step + 1} ---")
            data = self.controller.observe()
            url, title, elements = data["url"], data["title"], data["elements"]
            
            is_new, node_id = self.tracker.add_node(url, title, elements, "")
            
            # Update screenshot path after getting ID
            screenshot_path = f"screenshots/{node_id}.png"
            self.controller.page.screenshot(path=screenshot_path)
            # Find the node and update its screenshot path
            for n in self.tracker.graph.nodes:
                if n.id == node_id:
                    n.screenshot = screenshot_path
            
            print(f"Current State: {node_id} {'(NEW)' if is_new else '(VISITED)'} - {title}")
            
            if current_node_id:
                # We transitioned from current_node_id to node_id
                self.tracker.add_edge(current_node_id, node_id, actions_history[-1])
            
            action = self.ask_llm(url, elements, actions_history)
            print(f"LLM Decision: {action.type} on {action.target} - {action.description}")
            
            if action.type == "finish":
                break
                
            self.controller.execute_action(action)
            actions_history.append(action)
            current_node_id = node_id
            
        print("Exploration Finished.")
        with open("graph_output.json", "w") as f:
            f.write(self.tracker.to_json())
        print("Graph saved to graph_output.json")

def main():
    target_url = "https://example.com"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        agent = Agent(page)
        agent.run(target_url, max_steps=5)
        
        browser.close()

if __name__ == "__main__":
    main()
