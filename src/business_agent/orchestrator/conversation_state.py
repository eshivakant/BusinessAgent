"""Conversation state management for multi-turn interactive flows."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class ConversationFlow(str, Enum):
    """Type of conversation flow."""
    PROPERTY_ADD = "property_add"
    MORTGAGE_ADD = "mortgage_add"
    TENANT_ADD = "tenant_add"
    MAINTENANCE_ADD = "maintenance_add"


@dataclass
class ConversationState:
    """Tracks state for a multi-turn conversation."""
    user_id: str
    flow: ConversationFlow
    step: str
    data: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def update_step(self, step: str) -> None:
        """Move to next step."""
        self.step = step
        self.updated_at = datetime.now(timezone.utc)
    
    def set_data(self, key: str, value: Any) -> None:
        """Store data for this conversation."""
        self.data[key] = value
        self.updated_at = datetime.now(timezone.utc)
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """Retrieve data from this conversation."""
        return self.data.get(key, default)


class ConversationManager:
    """Manages active conversations for users."""
    
    def __init__(self) -> None:
        self._conversations: Dict[str, ConversationState] = {}
    
    def start_conversation(
        self,
        user_id: str,
        flow: ConversationFlow,
        initial_step: str,
        initial_data: Optional[Dict[str, Any]] = None
    ) -> ConversationState:
        """Start a new conversation for a user."""
        state = ConversationState(
            user_id=user_id,
            flow=flow,
            step=initial_step,
            data=initial_data or {}
        )
        self._conversations[user_id] = state
        return state
    
    def get_conversation(self, user_id: str) -> Optional[ConversationState]:
        """Get active conversation for a user."""
        return self._conversations.get(user_id)
    
    def end_conversation(self, user_id: str) -> None:
        """End conversation for a user."""
        self._conversations.pop(user_id, None)
    
    def clear_all(self) -> None:
        """Clear all conversations (for testing)."""
        self._conversations.clear()
