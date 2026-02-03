"""Channel Router — Orchestrates inbound→Emma→outbound message flow.

Flow:
1. Receive inbound message from channel webhook
2. Verify/pair external user via PairingService
3. Route through IntentRouter → LangGraph
4. Send response back through the originating channel
"""
import logging
import uuid
from typing import Any, Dict, Optional

from app.channels.base import BaseChannel
from app.channels.telegram_channel import TelegramChannel
from app.channels.whatsapp_channel import WhatsAppChannel
from app.channels.slack_channel import SlackChannel
from app.channels.email_channel import EmailChannel
from app.services.pairing_service import pairing_service

logger = logging.getLogger(__name__)

# Channel type → class mapping
CHANNEL_REGISTRY = {
    "telegram": TelegramChannel,
    "whatsapp": WhatsAppChannel,
    "slack": SlackChannel,
    "email": EmailChannel,
}


class ChannelRouter:
    """Routes messages between external channels and Emma AI."""

    def __init__(self):
        self._active_channels: Dict[str, BaseChannel] = {}

    def get_channel_instance(
        self,
        channel_id: str,
        channel_type: str,
        config: Dict[str, Any],
        credentials: Optional[str] = None,
    ) -> BaseChannel:
        """Get or create a channel instance."""
        if channel_id in self._active_channels:
            return self._active_channels[channel_id]

        channel_cls = CHANNEL_REGISTRY.get(channel_type)
        if not channel_cls:
            raise ValueError(f"Unknown channel type: {channel_type}")

        channel = channel_cls(
            channel_id=channel_id,
            config=config,
            credentials=credentials,
        )
        self._active_channels[channel_id] = channel
        return channel

    async def route_inbound(
        self,
        channel_id: str,
        channel_type: str,
        config: Dict[str, Any],
        credentials: Optional[str],
        webhook_data: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Process an inbound message through Emma and respond.

        Returns:
            Dict with response details
        """
        channel = self.get_channel_instance(channel_id, channel_type, config, credentials)

        # 1. Parse inbound message
        parsed = await channel.parse_inbound(webhook_data)
        sender_id = parsed.get("sender_id", "")
        content = parsed.get("content", "")

        if not content:
            return {"status": "ignored", "reason": "empty_message"}

        logger.info(f"Inbound [{channel_type}] from {sender_id}: {content[:100]}")

        # 2. Verify user pairing
        pairing = await pairing_service.get_pairing(tenant_id, channel_type, sender_id)
        reply_to = parsed.get("channel_id") or parsed.get("chat_id") or sender_id

        if not pairing:
            # Send pairing instructions
            pairing_code = await pairing_service.generate_pairing_code(
                tenant_id, channel_type, sender_id
            )
            await channel.send_message(
                to=reply_to,
                content=(
                    f"👋 ¡Hola! Soy Emma AI. Para vincular tu cuenta, "
                    f"ve a NouxCubeIA → Configuración → Canales y usa el código: **{pairing_code}**"
                ),
            )
            return {"status": "pairing_required", "code": pairing_code}

        user_id = pairing["user_id"]

        # 3. Execute through Emma
        try:
            from app.services.emma_background_service import emma_background_service
            result = await emma_background_service.proactive_analysis(
                tenant_id=tenant_id,
                analysis_type="channel_query",
                query=content,
                context={
                    "channel_type": channel_type,
                    "sender_id": sender_id,
                    "user_id": user_id,
                },
            )
            answer = result.get("answer", "Lo siento, no pude procesar tu consulta.")
        except Exception as e:
            logger.error(f"Emma execution failed for channel message: {e}")
            answer = "⚠️ Hubo un error procesando tu consulta. Inténtalo de nuevo."

        # 4. Send response (use channel_id for Slack, chat_id for Telegram)
        reply_to = parsed.get("channel_id") or parsed.get("chat_id") or sender_id
        send_result = await channel.send_message(
            to=reply_to,
            content=answer,
        )

        return {
            "status": "responded",
            "sender_id": sender_id,
            "user_id": user_id,
            "response_sent": send_result.get("success", False),
        }


# Global singleton
channel_router = ChannelRouter()
