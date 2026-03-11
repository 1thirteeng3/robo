import os
import httpx
from typing import Annotated
from pathlib import Path

from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks
from loguru import logger

from nanobot.providers.abacus_provider import AbacusProvider
from nanobot.session.manager import SessionManager
from nanobot.agent.loop import AgentLoop
from nanobot.bus.queue import MessageBus
from nanobot.agent.tools.obsidian import ObsidianTool
from nanobot.agent.tools.black_ops import BlackOpsScrapeTool

app = FastAPI(title="Pandaemon Webhook Gateway")

# Configuration (from env or hardcoded as per local implementation preferences)
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "super-secret-token")
ABACUS_API_KEY = os.environ.get("ABACUS_API_KEY", "")
WORKSPACE_DIR = Path(os.environ.get("WORKSPACE_DIR", "."))
ALLOWED_CHAT_ID = os.environ.get("ALLOWED_CHAT_ID", "")

# Global instances that are lightweight and can persist 
provider = AbacusProvider(api_key=ABACUS_API_KEY)
# We instantiate session manager per request as per instructions or globally since it's lightweight
# session_manager = SessionManager(WORKSPACE_DIR)

async def _send_telegram_message(chat_id: int, text: str):
    """Send text message back to Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(url, json=payload)
            r.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

async def process_telegram_update(update_data: dict):
    """Processes the message using the ephemeral AgentLoop and saves history."""
    try:
        message = update_data.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "").strip()

        if not text:
            return

        # Initialize the heavy parts ephemerally
        bus = MessageBus()
        session_manager = SessionManager(WORKSPACE_DIR)
        
        loop = AgentLoop(
            bus=bus,
            provider=provider,
            workspace=WORKSPACE_DIR,
            session_manager=session_manager
        )
        loop.tools.register(ObsidianTool(WORKSPACE_DIR))
        loop.tools.register(BlackOpsScrapeTool())

        session_key = f"telegram:{chat_id}"
        logger.info(f"Processing message '{text}' for session '{session_key}'")

        # Process the message and get response
        response_text = await loop.process_direct(
            content=text,
            session_key=session_key,
            channel="telegram",
            chat_id=str(chat_id)
        )

        if response_text:
            await _send_telegram_message(chat_id, response_text)

    except Exception as e:
        logger.exception("Error processing update within AgentLoop")

@app.post("/telegram-webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None
):
    """Receives Telegram webhook events securely."""
    # 1. Rigorous security validation of the webhook token
    if not x_telegram_bot_api_secret_token or x_telegram_bot_api_secret_token != TELEGRAM_WEBHOOK_SECRET:
        logger.warning(f"Unauthorized access attempt to webhook with token: {x_telegram_bot_api_secret_token}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # 2. Extract chat_id to validate against whitelist
    message = update_data.get("message", {})
    chat = message.get("chat", {})
    chat_id = chat.get("id")

    # If it's not a message event or chat_id is missing, acknowledge and ignore
    if not chat_id:
        return {"status": "ok"}

    # Whitelist rigid security check
    if ALLOWED_CHAT_ID and str(chat_id) != str(ALLOWED_CHAT_ID):
        logger.warning(f"Message from unapproved chat_id: {chat_id}")
        return {"status": "ok"} # Return 200 so Telegram doesn't retry

    # 3. Queue the cold start and inference process as a background task
    # so we return 200 OK to Telegram immediately.
    background_tasks.add_task(process_telegram_update, update_data)

    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
