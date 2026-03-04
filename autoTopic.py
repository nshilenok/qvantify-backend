"""Backward-compatible re-export. Real implementation in interview.topic_engine."""
from interview.topic_engine import TOOL_SPEC as function
from interview.topic_engine import handle_tool_call as switchTopic
from interview.topic_engine import force_switch_from_text as forceSwitchFromText

__all__ = ["function", "switchTopic", "forceSwitchFromText"]
