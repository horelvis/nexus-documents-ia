"""Email channel implementation using aiosmtplib for sending."""
import logging
from email.message import EmailMessage
from typing import Any, Dict, Optional

from .base import BaseChannel

logger = logging.getLogger(__name__)


class EmailChannel(BaseChannel):
    """Email channel using SMTP for outbound and webhook for inbound."""

    @property
    def channel_type(self) -> str:
        return "email"

    async def send_message(self, to: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        try:
            import aiosmtplib

            smtp_host = self.config.get("smtp_host", "localhost")
            smtp_port = self.config.get("smtp_port", 587)
            smtp_user = self.config.get("smtp_user", "")
            smtp_pass = self._credentials or self.config.get("smtp_password", "")
            from_email = self.config.get("from_email", smtp_user)

            subject = (metadata or {}).get("subject", "Emma AI — Notificación")

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = from_email
            msg["To"] = to
            msg.set_content(content)

            # HTML version if provided
            html_content = (metadata or {}).get("html")
            if html_content:
                msg.add_alternative(html_content, subtype="html")

            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=True,
            )
            return {"success": True, "message_id": msg["Message-ID"]}

        except ImportError:
            logger.error("aiosmtplib not installed — cannot send email")
            return {"success": False, "error": "aiosmtplib not installed"}
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return {"success": False, "error": str(e)}

    async def parse_inbound(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "sender_id": webhook_data.get("from", ""),
            "content": webhook_data.get("text", webhook_data.get("body", "")),
            "message_id": webhook_data.get("message_id", ""),
            "subject": webhook_data.get("subject", ""),
            "raw": webhook_data,
        }

    async def health_check(self) -> Dict[str, Any]:
        try:
            import aiosmtplib

            smtp_host = self.config.get("smtp_host", "localhost")
            smtp_port = self.config.get("smtp_port", 587)

            smtp = aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port)
            await smtp.connect()
            await smtp.quit()
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
