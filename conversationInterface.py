"""Backward-compatible re-export. Real implementation in interview.conversation."""
from interview.conversation import conversation
from interview.topic_engine import strip_raw_tool_text as _strip_raw_tool_text

__all__ = ["conversation", "_strip_raw_tool_text"]
