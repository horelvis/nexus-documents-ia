"""Channel Router — Orchestrates inbound→Emma→outbound message flow.

Flow:
1. Receive inbound message from channel webhook
2. Check if Emma should respond (groups: only if mentioned or relevant)
3. Verify/pair external user via PairingService
4. Route through Emma with social prompt
5. Send response back through the originating channel
"""
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from app.channels.base import BaseChannel
from app.channels.telegram_channel import TelegramChannel
from app.channels.whatsapp_channel import WhatsAppChannel
from app.channels.slack_channel import SlackChannel
from app.channels.email_channel import EmailChannel
from app.services.pairing_service import pairing_service

logger = logging.getLogger(__name__)

# Keywords that suggest Emma should respond even without explicit mention
RELEVANCE_KEYWORDS = [
    "documento", "contrato", "factura", "análisis", "riesgo",
    "vencimiento", "cumplimiento", "rgpd", "legal", "compliance",
    "gdpr", "privacy", "privacidad", "clausula", "cláusula",
    "expediente", "informe", "normativa", "ley", "artículo",
]

# Channel type → class mapping
CHANNEL_REGISTRY = {
    "telegram": TelegramChannel,
    "whatsapp": WhatsAppChannel,
    "slack": SlackChannel,
    "email": EmailChannel,
}


def _should_respond_in_group(
    content: str,
    is_mentioned: bool,
    is_group: bool,
    is_thread_reply: bool = False,
) -> bool:
    """Determine if Emma should respond to a group message.

    Emma only responds when she can add value:
    - When explicitly mentioned
    - When replying in a thread (continuing a conversation)
    - When someone asks about documents, contracts, legal topics
    - When someone asks a direct question she can answer

    Args:
        content: The message text
        is_mentioned: Whether Emma was explicitly mentioned
        is_group: Whether this is a group chat
        is_thread_reply: Whether this is a reply in an existing thread

    Returns:
        True if Emma should respond
    """
    # Always respond in private chats
    if not is_group:
        return True

    # Always respond if explicitly mentioned
    if is_mentioned:
        logger.info(f"Responding: Emma was mentioned")
        return True

    # Always respond to thread replies (user is continuing a conversation)
    if is_thread_reply:
        logger.info(f"Responding: Thread reply detected (continuing conversation)")
        return True

    content_lower = content.lower().strip()

    # Skip very short messages
    if len(content_lower) < 5:
        return False

    # Skip casual chat / small talk
    casual_patterns = [
        "jaja", "jeje", "lol", "xd", "haha", "😂", "🤣",
        "ok", "vale", "bien", "bueno", "claro", "sí", "si", "no",
        "gracias", "thanks", "thx", "👍", "👌", "🙏",
        "hola", "hey", "buenas", "qué tal", "que tal",
        "uff", "vaya", "madre mía", "ostras", "wow",
        "tiempo", "clima", "lluvia", "sol", "frío", "calor",
        "fin de semana", "finde", "vacaciones", "partido",
    ]
    if any(pattern in content_lower for pattern in casual_patterns):
        # Unless it also contains a document-related keyword
        if not any(kw in content_lower for kw in RELEVANCE_KEYWORDS):
            logger.debug(f"Skipping casual message: '{content[:30]}...'")
            return False

    # Respond if it looks like a question about relevant topics
    is_question = "?" in content or any(
        q in content_lower for q in [
            "qué", "que", "cómo", "como", "cuál", "cual",
            "dónde", "donde", "cuándo", "cuando", "cuánto", "cuanto",
            "por qué", "por que", "quién", "quien",
            "puedo", "puedes", "puede", "hay", "tiene", "tengo",
        ]
    )

    # Check for relevance keywords
    has_relevant_keyword = any(kw in content_lower for kw in RELEVANCE_KEYWORDS)

    if has_relevant_keyword:
        logger.info(f"Responding: relevant keyword found")
        return True

    if is_question and len(content_lower) > 15:
        # It's a substantial question - check if Emma can help
        # Look for question patterns that suggest document/legal help
        help_patterns = [
            "buscar", "busca", "encontrar", "encuentra",
            "analizar", "analiza", "revisar", "revisa",
            "necesito", "quiero", "podrías", "podrias",
            "ayuda", "help", "info", "información",
        ]
        if any(p in content_lower for p in help_patterns):
            logger.info(f"Responding: help request detected")
            return True

    logger.debug(f"Skipping message (not relevant): '{content[:30]}...'")
    return False


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

        # Skip bot messages and duplicates
        if parsed.get("is_bot") or parsed.get("is_duplicate"):
            return {"status": "ignored", "reason": "bot_or_duplicate"}

        if not content:
            return {"status": "ignored", "reason": "empty_message"}

        # 2. Check if Emma should respond (group logic)
        is_group = parsed.get("is_group", False)
        is_mentioned = parsed.get("is_mentioned", False)
        group_name = parsed.get("group_name", "")

        # Detect thread replies: if thread_ts exists and differs from message_id (ts),
        # it's a reply in an existing thread - Emma should respond to continue conversation
        thread_ts = parsed.get("thread_ts", "")
        message_ts = parsed.get("message_id", "")
        is_thread_reply = bool(thread_ts and thread_ts != message_ts)

        if not _should_respond_in_group(content, is_mentioned, is_group, is_thread_reply):
            return {
                "status": "ignored",
                "reason": "group_not_relevant",
                "is_group": is_group,
                "is_mentioned": is_mentioned,
                "is_thread_reply": is_thread_reply,
            }

        logger.info(
            f"Inbound [{channel_type}] from {sender_id}"
            f"{' (group: ' + group_name + ')' if is_group else ''}: {content[:100]}"
        )

        # 3. Verify user pairing
        pairing = await pairing_service.get_pairing(tenant_id, channel_type, sender_id)
        reply_to = parsed.get("channel_id") or parsed.get("chat_id") or sender_id

        if not pairing:
            # Send pairing instructions (friendlier tone for social channels)
            pairing_code = await pairing_service.generate_pairing_code(
                tenant_id, channel_type, sender_id
            )
            await channel.send_message(
                to=reply_to,
                content=(
                    f"👋 ¡Hola! Soy Emma, tu asistente de documentos. "
                    f"Para que pueda ayudarte, necesito que vincules tu cuenta.\n\n"
                    f"Ve a NouxCubeIA → Configuración → Canales y usa este código: **{pairing_code}**\n\n"
                    f"¡Solo toma un momento! 🔗"
                ),
            )
            return {"status": "pairing_required", "code": pairing_code}

        user_id = pairing["user_id"]

        # 4. Build deterministic session_id for conversation memory persistence
        # Format: {channel_type}:{channel_id}:{thread_or_chat}:{user_id}
        # This ensures the same conversation always uses the same session_id
        session_key_parts = [channel_type]

        if channel_type == "slack":
            # For Slack: use channel + thread_ts (or channel if no thread)
            slack_channel = parsed.get("channel_id", "")
            thread_ts = parsed.get("thread_ts", "")
            session_key_parts.extend([slack_channel, thread_ts or "main"])
        elif channel_type in ("telegram", "whatsapp"):
            # For Telegram/WhatsApp: use chat_id
            chat_id = parsed.get("chat_id", sender_id)
            session_key_parts.append(chat_id)
        else:
            # Default: use sender_id
            session_key_parts.append(sender_id)

        # Add user_id to make it user-specific within groups
        session_key_parts.append(user_id[:12] if user_id else "anon")
        session_id = ":".join(session_key_parts)

        logger.info(f"📝 Session ID for conversation memory: {session_id}")

        # 5. Execute through Emma with social channel context
        try:
            from app.services.emma_background_service import emma_background_service

            result = await emma_background_service.channel_query(
                tenant_id=tenant_id,
                query=content,
                channel_type=channel_type,
                user_id=user_id,
                is_group=is_group,
                group_name=group_name,
                channel_config=config,  # Pass channel config (includes location)
                session_id=session_id,  # Pass deterministic session_id for memory
            )
            answer = result.get("answer", "")

            # Fallback message if empty
            if not answer:
                answer = "🤔 No pude procesar tu consulta. ¿Puedes reformularla?"

        except Exception as e:
            logger.error(f"Emma execution failed for channel message: {e}", exc_info=True)
            answer = "⚠️ Ups, hubo un problema. ¿Puedes intentarlo de nuevo?"

        # 6. Send response (in thread for Slack)
        reply_to = parsed.get("channel_id") or parsed.get("chat_id") or sender_id

        # Include thread_ts for Slack to reply in the same thread
        send_metadata = {}
        if channel_type == "slack" and thread_ts:
            send_metadata["thread_ts"] = thread_ts

        send_result = await channel.send_message(
            to=reply_to,
            content=answer,
            metadata=send_metadata,
        )

        return {
            "status": "responded",
            "sender_id": sender_id,
            "user_id": user_id,
            "is_group": is_group,
            "response_sent": send_result.get("success", False),
        }


# Global singleton
channel_router = ChannelRouter()
