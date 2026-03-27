import sys
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright

from browser import navigate, extract_elements, execute_action
from llm import ask_llm
from state_tracker import Action, GraphTracker

load_dotenv()

MAX_STEPS = 15


def make_run_dir(url: str) -> Path:
    domain = urlparse(url).netloc.replace("www.", "")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path("logs") / f"{timestamp}_{domain}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def setup_logger(run_dir: Path) -> logging.Logger:
    logger = logging.getLogger("agent")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")

    fh = logging.FileHandler(run_dir / "run.log")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def run(url: str, max_steps: int = MAX_STEPS, username: str | None = None, password: str | None = None):
    run_dir = make_run_dir(url)
    log = setup_logger(run_dir)
    client = OpenAI()
    tracker = GraphTracker()

    history = []        # list of action dicts passed to LLM for context
    visited_urls = []   # list of URLs seen, passed to LLM to avoid re-exploring
    blocked_targets = []# element ids that triggered external navigation
    current_node_id = None
    credentials = {"username": username, "password": password} if username and password else None

    log.info(f"Run directory : {run_dir}")
    log.info(f"Target URL    : {url}")
    log.info(f"Max steps     : {max_steps}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        navigate(page, url, log)

        for step in range(1, max_steps + 1):
            log.info(f"--- Step {step}/{max_steps} ---")

            # --- Observe ---
            elements = extract_elements(page)
            current_url = page.url
            current_title = page.title()
            log.info(f"URL   : {current_url}")
            log.info(f"Title : {current_title}")
            log.info(f"Elements found: {len(elements)}")

            # --- Fingerprint + record state ---
            screenshot_path = str(run_dir / f"step_{step:02d}.png")
            page.screenshot(path=screenshot_path)

            is_new, node_id = tracker.add_node(current_url, current_title, elements, screenshot_path)
            log.info(f"State : {node_id} {'(NEW)' if is_new else '(REVISIT)'}")

            if current_node_id and current_node_id != node_id and history:
                tracker.add_edge(current_node_id, node_id, Action(**history[-1]))

            if current_url not in visited_urls:
                visited_urls.append(current_url)

            current_node_id = node_id

            # --- Decide ---
            action = ask_llm(client, current_url, elements, history, visited_urls, blocked_targets, log, credentials)
            log.info(f"Action: {action.type} | target={action.target}")
            log.debug(f"Reason: {action.description}")

            # --- Act ---
            origin_domain = urlparse(current_url).netloc
            should_continue = execute_action(page, action, log)
            history.append(action.model_dump())

            if not should_continue:
                break

            # If we navigated off-domain, go back and block that target
            new_domain = urlparse(page.url).netloc
            if new_domain and new_domain != origin_domain:
                log.warning(f"Left domain ({new_domain}), navigating back ...")
                if action.target and action.target not in blocked_targets:
                    blocked_targets.append(action.target)
                page.go_back()
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    page.wait_for_load_state("load")

        # --- Save graph ---
        graph_path = run_dir / "graph_output.json"
        graph_path.write_text(tracker.to_json())
        log.info(f"Graph saved   : {graph_path}")
        log.info(f"States found  : {len(tracker.graph.nodes)}")
        log.info(f"Transitions   : {len(tracker.graph.edges)}")
        log.info("Exploration complete.")

        browser.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    args = parser.parse_args()
    run(args.url, max_steps=args.max_steps, username=args.username, password=args.password)
