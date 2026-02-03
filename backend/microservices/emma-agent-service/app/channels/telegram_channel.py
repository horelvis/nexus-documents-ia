"""Telegram channel implementation using python-telegram-bot."""
import logging
import re
from typing import Any, Dict, Optional

import httpx

from .base import BaseChannel

logger = logging.getLogger(__name__)

# Bot username cache (set after health_check)
_BOT_USERNAME: Optional[str] = None


class TelegramChannel(BaseChannel):
    """Telegram Bot API channel."""

    @property
    def channel_type(self) -> str:
        return "telegram"

    def _get_token(self) -> str:
        return self.config.get("bot_token", self._credentials or "")

    async def send_message(self, to: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        token = self._get_token()
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json={
                "chat_id": to,
                "text": content,
                "parse_mode": "Markdown",
            })
            result = response.json()

        if result.get("ok"):
            return {"success": True, "message_id": result["result"]["message_id"]}
        else:
            logger.error(f"Telegram send failed: {result}")
            return {"success": False, "error": result.get("description", "Unknown error")}

    async def parse_inbound(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        global _BOT_USERNAME
        message = webhook_data.get("message", {})
        chat = message.get("chat", {})
        text = message.get("text", "")

        # Detect chat type (private, group, supergroup, channel)
        chat_type = chat.get("type", "private")
        is_group = chat_type in ("group", "supergroup")
        group_name = chat.get("title", "") if is_group else ""

        # Check if bot is mentioned
        is_mentioned = False

        # 1. Check @username mentions
        if _BOT_USERNAME:
            is_mentioned = f"@{_BOT_USERNAME}".lower() in text.lower()

        # 2. Check entities for bot_command or mention
        entities = message.get("entities", [])
        for entity in entities:
            if entity.get("type") == "mention":
                # Extract mentioned username
                offset = entity.get("offset", 0)
                length = entity.get("length", 0)
                mentioned = text[offset:offset + length]
                if _BOT_USERNAME and mentioned.lower() == f"@{_BOT_USERNAME}".lower():
                    is_mentioned = True
                    break
            elif entity.get("type") == "bot_command":
                # Bot commands like /help always target the bot
                is_mentioned = True
                break

        # 3. Check for Emma name mentions (conversational)
        emma_patterns = [
            r"\bemma\b",
            r"\bemma[,:\?!]",
            r"^emma\s",
            r"\soye\s+emma\b",
            r"\bhey\s+emma\b",
        ]
        for pattern in emma_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                is_mentioned = True
                break

        # Clean mentions from text for processing
        clean_text = text
        if _BOT_USERNAME:
            clean_text = re.sub(rf"@{_BOT_USERNAME}\s*", "", clean_text, flags=re.IGNORECASE)
        clean_text = clean_text.strip()

        return {
            "sender_id": str(message.get("from", {}).get("id", "")),
            "sender_name": message.get("from", {}).get("first_name", ""),
            "content": clean_text,
            "message_id": str(message.get("message_id", "")),
            "chat_id": str(chat.get("id", "")),
            "chat_type": chat_type,
            "is_group": is_group,
            "group_name": group_name,
            "is_mentioned": is_mentioned,
            "raw": webhook_data,
        }

    async def health_check(self) -> Dict[str, Any]:
        global _BOT_USERNAME
        token = self._get_token()
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                result = response.json()
            if result.get("ok"):
                bot_info = result["result"]
                _BOT_USERNAME = bot_info.get("username", "")
                logger.info(f"Telegram bot authenticated: @{_BOT_USERNAME}")
                return {
                    "status": "healthy",
                    "bot": _BOT_USERNAME,
                    "bot_id": bot_info.get("id"),
                }
            return {"status": "unhealthy", "error": result.get("description")}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
