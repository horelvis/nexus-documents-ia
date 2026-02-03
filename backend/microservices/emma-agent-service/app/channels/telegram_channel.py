"""Telegram channel implementation using python-telegram-bot."""
import logging
from typing import Any, Dict, Optional

import httpx

from .base import BaseChannel

logger = logging.getLogger(__name__)


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
        message = webhook_data.get("message", {})
        return {
            "sender_id": str(message.get("from", {}).get("id", "")),
            "sender_name": message.get("from", {}).get("first_name", ""),
            "content": message.get("text", ""),
            "message_id": str(message.get("message_id", "")),
            "chat_id": str(message.get("chat", {}).get("id", "")),
            "raw": webhook_data,
        }

    async def health_check(self) -> Dict[str, Any]:
        token = self._get_token()
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                result = response.json()
            if result.get("ok"):
                return {"status": "healthy", "bot": result["result"]["username"]}
            return {"status": "unhealthy", "error": result.get("description")}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
