"""Multi-channel messaging for Emma Reactive.

Each channel implements BaseChannel for send/receive/health_check.
The ChannelRouter orchestrates inbound→Emma→outbound flow.
"""
from .base import BaseChannel

__all__ = ["BaseChannel"]
