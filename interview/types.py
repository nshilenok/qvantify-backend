from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class ReplyInput:
    """Parsed, validated input from a POST /api/reply/ request."""
    message: str
    voice_input: bool = False
    audio_tokens: int = 0
    wants_stream: bool = False

    @classmethod
    def from_payload(cls, payload: dict, headers: Optional[dict] = None) -> "ReplyInput":
        message = payload.get("message")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("Missing JSON field: message")

        voice_input = bool(payload.get("voice_input"))
        audio_tokens_raw = payload.get("audio_tokens")
        try:
            audio_tokens = int(audio_tokens_raw) if audio_tokens_raw is not None else 0
        except Exception:
            audio_tokens = 0
        if not voice_input:
            audio_tokens = 0
        audio_tokens = max(0, audio_tokens)

        wants_stream = bool(payload.get("stream"))
        if headers and "text/event-stream" in (headers.get("Accept") or ""):
            wants_stream = True

        return cls(
            message=message,
            voice_input=voice_input,
            audio_tokens=audio_tokens,
            wants_stream=wants_stream,
        )


@dataclass
class ReplyResult:
    """Output from a single reply cycle (non-streaming or final streaming event)."""
    response_text: str
    topic_status: str
    defined_answers: Optional[str] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    debug: Optional[Dict[str, Any]] = None
    topic_switched: bool = False
    new_topic_id: Optional[str] = None

    def to_dict(self, version: str) -> dict:
        d: Dict[str, Any] = {
            "response": self.response_text,
            "status": self.topic_status,
            "answers": self.defined_answers,
            "progress": self.progress,
            "version": version,
        }
        if self.debug:
            d["_debug"] = self.debug
        return d


@dataclass
class AnalysisResult:
    """Outcome of an analysis run."""
    success: bool
    reason: str
    persona_label: Optional[str] = None
    findings_summary: Optional[str] = None
    sentiment: Optional[str] = None
    facts: Optional[str] = None
