"""Slack channel implementation via Web API."""
import logging
import re
from typing import Any, Dict, Optional, Set

import httpx

from .base import BaseChannel

logger = logging.getLogger(__name__)


def _clean_slack_text(text: str) -> str:
    """Clean Slack-specific formatting from message text.

    Removes:
    - User mentions: <@U0ACZTY6KED> -> ""
    - Channel mentions: <#C0ACZTY6KED|general> -> "#general"
    - URLs: <http://example.com|Example> -> "Example"
    - Special commands: <!here> <!channel> -> ""
    """
    if not text:
        return ""

    # Remove user mentions <@USERID>
    text = re.sub(r"<@[A-Z0-9]+>", "", text)

    # Replace channel mentions <#CHANNELID|name> with #name
    text = re.sub(r"<#[A-Z0-9]+\|([^>]+)>", r"#\1", text)

    # Replace URLs <url|label> with label, or just url if no label
    text = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", text)
    text = re.sub(r"<(https?://[^>]+)>", r"\1", text)

    # Remove special mentions
    text = re.sub(r"<!(?:here|channel|everyone)>", "", text)

    # Clean up extra whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text

# Track processed message IDs to prevent duplicates (Slack retries)
_processed_messages: Set[str] = set()
_MAX_PROCESSED_CACHE = 1000


class SlackChannel(BaseChannel):
    """Slack Bot using Web API."""

    _bot_user_id: Optional[str] = None  # Cached bot user ID

    @property
    def channel_type(self) -> str:
        return "slack"

    def _get_token(self) -> str:
        return self._credentials or self.config.get("bot_token", "")

    async def send_message(self, to: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        token = self._get_token()
        url = "https://slack.com/api/chat.postMessage"
        metadata = metadata or {}

        # Build message payload
        payload = {
            "channel": to,
            "text": content,
        }

        # Reply in thread if thread_ts is provided (keeps conversation in same thread)
        thread_ts = metadata.get("thread_ts")
        if thread_ts:
            payload["thread_ts"] = thread_ts
            logger.info(f"📎 Replying in Slack thread: {thread_ts}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=payload,
            )
            result = response.json()

        if result.get("ok"):
            return {"success": True, "message_id": result.get("ts")}
        else:
            logger.error(f"Slack send failed: {result.get('error')}")
            return {"success": False, "error": result.get("error", "Unknown")}

    async def parse_inbound(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        global _processed_messages

        event = webhook_data.get("event", {})
        message_id = event.get("ts", "")
        sender_id = event.get("user", "")

        # 1. Ignore bot messages (bot_id present or subtype is bot_message)
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            logger.debug(f"Ignoring bot message: {message_id}")
            return {"sender_id": "", "content": "", "message_id": message_id, "is_bot": True, "raw": webhook_data}

        # 2. Ignore if sender is the bot itself (compare with cached bot_user_id)
        if self._bot_user_id and sender_id == self._bot_user_id:
            logger.debug(f"Ignoring message from bot user: {sender_id}")
            return {"sender_id": "", "content": "", "message_id": message_id, "is_bot": True, "raw": webhook_data}

        # 3. Deduplicate (Slack retries if response takes >3s)
        if message_id in _processed_messages:
            logger.debug(f"Ignoring duplicate message: {message_id}")
            return {"sender_id": "", "content": "", "message_id": message_id, "is_duplicate": True, "raw": webhook_data}

        # Track this message
        _processed_messages.add(message_id)
        if len(_processed_messages) > _MAX_PROCESSED_CACHE:
            # Remove oldest entries (set doesn't preserve order, but good enough)
            _processed_messages = set(list(_processed_messages)[-500:])

        # Clean Slack formatting from text (remove mentions, etc.)
        raw_text = event.get("text", "")
        clean_text = _clean_slack_text(raw_text)

        logger.debug(f"Slack text cleaned: '{raw_text}' -> '{clean_text}'")

        # Detect if this is a direct message or group/channel
        channel_type_raw = event.get("channel_type", "")
        is_dm = channel_type_raw == "im"
        is_group = not is_dm  # channel or group

        # Check if bot was mentioned in the original text
        is_mentioned = False
        if self._bot_user_id:
            is_mentioned = f"<@{self._bot_user_id}>" in raw_text

        # Also check for Emma name mentions (conversational)
        emma_mentioned = any(
            pattern in raw_text.lower()
            for pattern in ["emma", "oye emma", "hey emma"]
        )
        is_mentioned = is_mentioned or emma_mentioned

        # Thread tracking: thread_ts identifies the thread, or use message ts for new threads
        thread_ts = event.get("thread_ts") or event.get("ts", "")

        return {
            "sender_id": sender_id,
            "content": clean_text,
            "message_id": message_id,
            "channel_id": event.get("channel", ""),
            "thread_ts": thread_ts,  # For conversation memory persistence
            "chat_type": "dm" if is_dm else "channel",
            "is_group": is_group,
            "group_name": "",  # Would need API call to get channel name
            "is_mentioned": is_mentioned,
            "raw": webhook_data,
        }

    async def health_check(self) -> Dict[str, Any]:
        token = self._get_token()
        url = "https://slack.com/api/auth.test"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                )
                result = response.json()
            if result.get("ok"):
                # Cache bot user ID to filter out our own messages
                self._bot_user_id = result.get("user_id")
                SlackChannel._bot_user_id = self._bot_user_id  # Class-level cache
                logger.info(f"Slack bot authenticated: {result.get('user')} (ID: {self._bot_user_id})")
                return {"status": "healthy", "bot": result.get("user"), "bot_user_id": self._bot_user_id}
            return {"status": "unhealthy", "error": result.get("error")}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
