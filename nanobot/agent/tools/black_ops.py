"""Black Ops: local, headless web automation via Playwright."""

from typing import Any
from loguru import logger
from playwright.async_api import async_playwright

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
        logger.info(f"Black Ops engaged: navigating to {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
                )
                
                # Wait until domcontentloaded to handle most SPA
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
                # Optional small wait to allow JS dynamic injections to finish
                await page.wait_for_timeout(2000)
                
                # Extract clean innerText
                inner_text = await page.evaluate("() => document.body.innerText")
                await browser.close()
                
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
