"""Base channel abstract class for multi-channel messaging."""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseChannel(ABC):
    """Abstract base for all messaging channels (WhatsApp, Telegram, Slack, Email)."""

    def __init__(self, channel_id: str, config: Dict[str, Any], credentials: Optional[str] = None):
        self.channel_id = channel_id
        self.config = config
        self._credentials = credentials

    @property
    @abstractmethod
    def channel_type(self) -> str:
        """Return the channel type identifier."""
        ...

    @abstractmethod
    async def send_message(self, to: str, content: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
        """Send a message to an external user.

        Args:
            to: External user identifier (phone, chat_id, channel, email)
            content: Message text
            metadata: Optional extra data (attachments, buttons, etc.)

        Returns:
            Dict with send status and message ID
        """
        ...

    @abstractmethod
    async def parse_inbound(self, webhook_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse an inbound webhook payload into a normalized message.

        Returns:
            Dict with keys: sender_id, content, message_id, raw
        """
        ...

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """Check channel connectivity."""
        ...

    async def initialize(self):
        """Optional initialization (e.g., register webhooks)."""
        pass

    async def shutdown(self):
        """Optional cleanup."""
        pass
