"""Black Ops: local, headless web automation via Playwright."""

from typing import Any
from loguru import logger
from playwright.sync_api import sync_playwright

from nanobot.agent.tools.base import Tool

class BlackOpsScrapeTool(Tool):
    """Headless web scraping tool using Playwright to handle JavaScript running sites."""

    @property
    def name(self) -> str:
        return "black_ops_scrape"

    @property
    def description(self) -> str:
        return "Opens a headless browser, navigates to a URL, and extracts the innerText of the page. Use this for single-page apps or sites that require JS execution."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The target URL to scrape"}
            },
            "required": ["url"],
        }

    async def execute(self, url: str, **kwargs: Any) -> str:
        # Note: The Tool base interface uses async def execute, but we can safely block the thread
        # here because this tool will be called from a thread pool executor or it's an I/O operation 
        # that executes safely in the webhook route instance. Wait, the framework `async def execute` 
        # means we should probably run the blocking sync_playwright in a thread, OR we just use synchronous 
        # code here blocking the current task. Given the instruction: "refatore para playwright.sync_api ... a execução bloqueie a thread local", 
        # we will do exactly that.
        
        logger.info(f"Black Ops engaged: navigating to {url}")
        
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                )
                
                # Wait until domcontentloaded to handle most SPA
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # Optional small wait to allow JS dynamic injections to finish
                page.wait_for_timeout(2000)
                
                # Extract clean innerText
                inner_text = page.evaluate("() => document.body.innerText")
                browser.close()
                
                logger.info("Black Ops extraction complete.")
                
                if not inner_text:
                    return f"Successfully reached {url} but extracted content was empty."
                
                # Truncate if ridiculously large to fit in Context limit
                max_len = 60000 
                if len(inner_text) > max_len:
                    return inner_text[:max_len] + f"\n\n[TRUNCATED: original was {len(inner_text)} chars]"
                return inner_text

        except Exception as e:
            logger.error(f"Black Ops failure on {url}: {e}")
            return f"Error executing Black Ops scrape on {url}: {e}"
