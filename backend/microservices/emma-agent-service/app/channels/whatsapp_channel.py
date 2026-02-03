"""WhatsApp channel implementation via Twilio API."""
import logging
from typing import Any, Dict, Optional

import httpx

from .base import BaseChannel

logger = logging.getLogger(__name__)


class WhatsAppChannel(BaseChannel):
    """WhatsApp via Twilio API."""

    @property
    def channel_type(self) -> str:
        return "whatsapp"

    async def send_message(self, to: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        account_sid = self.config.get("account_sid", "")
        auth_token = self._credentials or self.config.get("auth_token", "")
        from_number = self.config.get("from_number", "")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                auth=(account_sid, auth_token),
                data={
                    "To": f"whatsapp:{to}",
                    "From": f"whatsapp:{from_number}",
                    "Body": content,
                },
            )
            if response.status_code == 201:
                result = response.json()
                return {"success": True, "message_id": result.get("sid")}
            else:
                logger.error(f"WhatsApp send failed: {response.text}")
                return {"success": False, "error": response.text}

    async def parse_inbound(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sender_id": webhook_data.get("From", "").replace("whatsapp:", ""),
            "content": webhook_data.get("Body", ""),
            "message_id": webhook_data.get("MessageSid", ""),
            "raw": webhook_data,
        }

    async def health_check(self) -> Dict[str, Any]:
        # Twilio doesn't have a simple health endpoint; verify credentials
        account_sid = self.config.get("account_sid", "")
        auth_token = self._credentials or ""
        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}.json"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, auth=(account_sid, auth_token))
            if response.status_code == 200:
                return {"status": "healthy"}
            return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
