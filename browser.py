import logging
from playwright.sync_api import Page
from state_tracker import Action


def navigate(page: Page, url: str, log: logging.Logger):
    page.goto(url)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        log.debug("networkidle timed out, falling back to load")
        page.wait_for_load_state("load")


def extract_elements(page: Page) -> list:
    return page.evaluate("""
        () => {
            const nodes = document.querySelectorAll(
                'button, a, input, textarea, select, [role="button"], [role="link"]'
            );
            const elements = [];
            const seenLinkPatterns = new Set();
            let i = 0;

            for (const el of nodes) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                if (el.disabled) continue;

                if (el.tagName === 'A') {
                    const href = el.getAttribute('href') || '';
                    const cleanPath = href.split('?')[0].split('#')[0];
                    const parts = cleanPath.split('/').filter(Boolean);
                    if (parts.length >= 1) {
                        // Include the last segment in the key if it's numeric (pagination).
                        // /page/2/ and /page/3/ get distinct keys; /author/X/ and /author/Y/ collapse.
                        const lastPart = parts[parts.length - 1];
                        const isNumeric = /^\d+$/.test(lastPart);
                        const pattern = isNumeric ? parts[0] + '/' + lastPart : parts[0];
                        if (seenLinkPatterns.has(pattern)) continue;
                        seenLinkPatterns.add(pattern);
                    }
                }

                // For inputs, use placeholder (stable) not value (changes when filled)
                const isInput = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA';
                const text = isInput
                    ? (el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 50)
                    : (el.innerText || '').trim().slice(0, 50);
                const aiId = 'el_' + i;
                el.setAttribute('data-ai-id', aiId);

                elements.push({
                    id: aiId,
                    text: text,
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute('type') || '',
                    selector: '[data-ai-id="' + aiId + '"]',
                });
                i++;
            }
            return elements;
        }
    """)


def execute_action(page: Page, action: Action, log: logging.Logger) -> bool:
    """Execute action on page. Returns False if action_type is 'finish'."""
    if action.type == "finish":
        log.info("LLM decided: finish")
        return False

    selector = f'[data-ai-id="{action.target}"]'
    try:
        if action.type == "click":
            page.click(selector, timeout=5000)
            log.info(f"Clicked      : {action.target}")
        elif action.type == "fill":
            page.fill(selector, action.value or "", timeout=5000)
            log.info(f"Filled       : {action.target} = {action.value!r}")
        elif action.type == "press":
            page.press(selector, action.key or "Enter", timeout=5000)
            log.info(f"Pressed      : {action.key!r} on {action.target}")
        else:
            log.warning(f"Unknown action type: {action.type!r}")
    except Exception as e:
        log.warning(f"Action failed ({action.type} on {action.target}): {e}")

    # Wait for page to settle after any action
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        page.wait_for_load_state("load")

    return True
