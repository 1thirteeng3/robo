"""Mycelium: RSS feed parsing and extraction using Abacus LLM."""

import os
import time
import asyncio
import sqlite3
from pathlib import Path
from loguru import logger
import feedparser

from pandaemon.providers.abacus_provider import AbacusProvider
from pandaemon.agent.tools.obsidian import ObsidianTool

WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", "."))
FEEDS_FILE = WORKSPACE_DIR / "feeds.txt"
DB_FILE = WORKSPACE_DIR / "mycelium_cache.db"
ABACUS_API_KEY = os.environ.get("ABACUS_API_KEY", "")

def setup_db():
    """Initialize SQLite database for tracking processed URLs."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS processed_urls
                 (url TEXT PRIMARY KEY, processed_at REAL)''')
    conn.commit()
    return conn

def is_processed(conn: sqlite3.Connection, url: str) -> bool:
    """Check if the URL exists in the cache."""
    c = conn.cursor()
    c.execute("SELECT 1 FROM processed_urls WHERE url=?", (url,))
    return c.fetchone() is not None

def mark_processed(conn: sqlite3.Connection, url: str):
    """Mark the URL as processed."""
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO processed_urls (url, processed_at) VALUES (?, ?)", (url, time.time()))
    conn.commit()

async def process_entry(entry, provider: AbacusProvider, obsidian_tool: ObsidianTool):
    """Evaluate entry and write to Obsidian if it is a signal."""
    title = entry.get("title", "")
    link = entry.get("link", "")
    summary = entry.get("summary", "")
    
    # Avoid too large inputs, truncating summary if necessary
    content_to_evaluate = f"Title: {title}\nLink: {link}\nContent:\n{summary[:3000]}"
    
    prompt = f"""Avalie este artigo. É ruído ou sinal? 
Um "sinal" é algo de extrema relevância técnica, inteligência artificial, engenharia reversa ou tendências econômicas. 
"Ruído" é clickbait, notícias triviais, política generalista ou drama de redes sociais.

Artigo:
{content_to_evaluate}

Instruções:
- Se for sinal, gere um resumo em 3 bullet points.
- Se for ruído, retorne exatamente: NULL
"""

    messages = [{"role": "user", "content": prompt}]
    response = await provider.chat_with_retry(messages=messages, max_tokens=1000, temperature=0.2)
    
    result = response.content.strip()
    if result == "NULL" or not result:
        logger.info(f"Discarding as noise: {title}")
        return

    logger.info(f"Signal detected: {title}")
    
    # Create Markdown note directly in Inbox
    safe_title = "".join([c if c.isalnum() else " " for c in title]).strip()
    filename = f"Inbox/RSS - {safe_title}.md"
    
    file_content = f"# {title}\n\n**Source:** {link}\n**Date:** {time.strftime('%Y-%m-%d')}\n\n## Summary\n{result}"
    
    await obsidian_tool.execute(filename=filename, content=file_content)


async def run():
    logger.info("Starting Mycelium...")
    if not ABACUS_API_KEY:
        logger.warning("ABACUS_API_KEY is not set. The LLM triage will rely on the default provider configuration which may fail without a key.")
        
    provider = AbacusProvider(api_key=ABACUS_API_KEY)
    obsidian_tool = ObsidianTool()

    if not FEEDS_FILE.exists():
        logger.error(f"Feeds file not found: {FEEDS_FILE}")
        return

    db_conn = setup_db()
    feeds = [url.strip() for url in FEEDS_FILE.read_text().splitlines() if url.strip() and not url.startswith("#")]

    for feed_url in feeds:
        logger.info(f"Parsing feed: {feed_url}")
        try:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries[:10]: # Process max 10 entries per feed to avoid LLM spam
                link = entry.get("link")
                if link and not is_processed(db_conn, link):
                    await process_entry(entry, provider, obsidian_tool)
                    mark_processed(db_conn, link)
                    # Simple rate limit for LLM provider
                    await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"Error parsing {feed_url}: {e}")

    db_conn.close()
    logger.info("Mycelium finished successfully.")

if __name__ == "__main__":
    asyncio.run(run())
