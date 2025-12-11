"""
Memory Protocol Data Types for Emma.

Defines the data structures used across the memory system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MessageRole(str, Enum):
    """Role of a message in conversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """
    A single message in a conversation.

    Attributes:
        role: Who sent the message (user, assistant, system, tool)
        content: The message content
        timestamp: When the message was created
        metadata: Additional data (tool_name, tool_result, etc.)
    """
    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create from dictionary."""
        return cls(
            role=MessageRole(data["role"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
            metadata=data.get("metadata", {})
        )

    def to_llm_format(self) -> Dict[str, str]:
        """Convert to format expected by LLM APIs."""
        return {
            "role": self.role.value,
            "content": self.content
        }


@dataclass
class ConversationContext:
    """
    Complete context for a conversation session.

    Includes message history, active documents, and session metadata.
    """
    session_id: str
    tenant_id: str
    user_id: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    active_documents: List[str] = field(default_factory=list)  # Document IDs in context
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def add_message(self, role: MessageRole, content: str, **metadata) -> None:
        """Add a new message to the conversation."""
        self.messages.append(Message(
            role=role,
            content=content,
            metadata=metadata
        ))
        self.updated_at = datetime.utcnow()

    def add_user_message(self, content: str, **metadata) -> None:
        """Add a user message."""
        self.add_message(MessageRole.USER, content, **metadata)

    def add_assistant_message(self, content: str, **metadata) -> None:
        """Add an assistant message."""
        self.add_message(MessageRole.ASSISTANT, content, **metadata)

    def add_tool_message(self, tool_name: str, result: str, **metadata) -> None:
        """Add a tool result message."""
        self.add_message(
            MessageRole.TOOL,
            result,
            tool_name=tool_name,
            **metadata
        )

    def get_history_for_llm(self, max_messages: int = 20) -> List[Dict[str, str]]:
        """
        Get conversation history formatted for LLM.

        Args:
            max_messages: Maximum messages to include (most recent)

        Returns:
            List of message dicts in LLM format
        """
        recent = self.messages[-max_messages:] if len(self.messages) > max_messages else self.messages
        return [msg.to_llm_format() for msg in recent]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "messages": [msg.to_dict() for msg in self.messages],
            "active_documents": self.active_documents,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationContext":
        """Deserialize from dictionary."""
        return cls(
            session_id=data["session_id"],
            tenant_id=data["tenant_id"],
            user_id=data.get("user_id"),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            active_documents=data.get("active_documents", []),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.utcnow(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow()
        )


@dataclass
class UserPreferences:
    """
    User preferences that persist across sessions.

    Includes display preferences, frequently used tools, and learned behaviors.
    """
    tenant_id: str
    user_id: str
    # Personalization fields
    display_name: Optional[str] = None  # User's display name for greeting
    preferred_language: str = "es"  # Preferred language
    response_style: str = "balanced"  # detailed, balanced, concise
    expertise_level: str = "general"  # beginner, general, expert
    # Legacy field for backward compatibility
    language: str = "es"  # Deprecated, use preferred_language
    visualization_preference: str = "auto"  # auto, table, chart, list
    max_results: int = 10
    enable_suggestions: bool = True
    favorite_tools: List[str] = field(default_factory=list)
    # Learning data
    frequent_queries: List[str] = field(default_factory=list)  # Last N queries
    frequent_documents: List[str] = field(default_factory=list)  # Most accessed docs
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "display_name": self.display_name,
            "preferred_language": self.preferred_language,
            "response_style": self.response_style,
            "expertise_level": self.expertise_level,
            "language": self.language,
            "visualization_preference": self.visualization_preference,
            "max_results": self.max_results,
            "enable_suggestions": self.enable_suggestions,
            "favorite_tools": self.favorite_tools,
            "frequent_queries": self.frequent_queries,
            "frequent_documents": self.frequent_documents,
            "custom_settings": self.custom_settings,
            "updated_at": self.updated_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPreferences":
        """Deserialize from dictionary."""
        return cls(
            tenant_id=data["tenant_id"],
            user_id=data["user_id"],
            # Personalization fields
            display_name=data.get("display_name"),
            preferred_language=data.get("preferred_language", "es"),
            response_style=data.get("response_style", "balanced"),
            expertise_level=data.get("expertise_level", "general"),
            # Legacy and display preferences
            language=data.get("language", "es"),
            visualization_preference=data.get("visualization_preference", "auto"),
            max_results=data.get("max_results", 10),
            enable_suggestions=data.get("enable_suggestions", True),
            favorite_tools=data.get("favorite_tools", []),
            frequent_queries=data.get("frequent_queries", []),
            frequent_documents=data.get("frequent_documents", []),
            custom_settings=data.get("custom_settings", {}),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.utcnow()
        )

    def record_query(self, query: str, max_queries: int = 50) -> None:
        """Record a user query for learning."""
        # Add to front, remove duplicates
        if query in self.frequent_queries:
            self.frequent_queries.remove(query)
        self.frequent_queries.insert(0, query)
        # Keep only last N
        self.frequent_queries = self.frequent_queries[:max_queries]
        self.updated_at = datetime.utcnow()

    def record_document_access(self, document_id: str, max_docs: int = 20) -> None:
        """Record document access for relevance."""
        if document_id in self.frequent_documents:
            self.frequent_documents.remove(document_id)
        self.frequent_documents.insert(0, document_id)
        self.frequent_documents = self.frequent_documents[:max_docs]
        self.updated_at = datetime.utcnow()
