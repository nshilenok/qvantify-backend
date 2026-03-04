"""Explicit request context for interview endpoints.

Replaces the implicit Flask ``g.*`` attribute bus with a typed, explicit
dataclass that route handlers build once and pass to all downstream modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from database import DB
    from .topic_engine import TopicEngine


@dataclass
class RequestContext:
    """All per-request state that used to live on Flask ``g.*``."""

    db: "DB"
    project_id: Optional[str] = None
    user_id: Optional[str] = None
    topic_handler: Optional["TopicEngine"] = None
    base_topic: Optional[str] = None
    current_topic: Optional[str] = None
    response_count: int = 0
    llm_purpose: str = "chat"
    llm_service: str = "core"
    topic_is_changing: bool = False
