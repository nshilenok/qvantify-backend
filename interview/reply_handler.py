"""Reply processing for the interview chat loop.

Terminal sink: receives user message, orchestrates LLM call + topic state,
produces a ReplyResult.  Does **not** trigger post-actions (analysis, session
close) -- those are the orchestrator's responsibility.
"""

import logging
import platform
from typing import Iterator, Optional, Tuple

from flask import g

from .conversation import conversation
from .topic_engine import TOOL_SPEC, handle_tool_call, strip_raw_tool_text
from .types import ReplyInput, ReplyResult
from llmInterface import LLM, strip_reasoning_leak

logger = logging.getLogger(__name__)


def _build_reply_debug(chat) -> Optional[dict]:
    """Return debug metadata dict for local dev, or None in production."""
    if platform.system() == 'Linux':
        return None
    try:
        topic_meta = chat._get_topic_meta(g.topic)
        ext_row = g.db.query_database_one(
            "SELECT external_id FROM respondents WHERE id=%s", (g.uuid,)
        )
        external_id = ext_row[0] if ext_row else None
        try:
            proj_row = g.db.query_database_one(
                "SELECT model, reasoning_effort FROM projects WHERE id=%s",
                (g.projectId,),
            )
            model = proj_row[0] if proj_row else None
            reasoning_effort = proj_row[1] if proj_row else None
        except Exception:
            model = None
            reasoning_effort = None
        developer_prompt = chat.retrieveTopic() + '\n \n' + chat.getDefaultPrompt()
        return {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "topic_title": topic_meta.get("title") if topic_meta else None,
            "user_id": g.uuid,
            "external_id": external_id,
            "developer_prompt": developer_prompt,
        }
    except Exception:
        logger.exception("_build_reply_debug failed")
        return None


def _build_fake_tool_response(tool_call_name: str):
    """Build a minimal response-like object compatible with autoTopic.switchTopic()."""
    class _Fn:
        def __init__(self, name): self.name = name
    class _ToolCall:
        def __init__(self, name): self.function = _Fn(name)
    class _Msg:
        def __init__(self, tool_calls): self.tool_calls = tool_calls
    class _Choice:
        def __init__(self, msg): self.message = msg
    class _Resp:
        def __init__(self, choices): self.choices = choices
    return _Resp([_Choice(_Msg([_ToolCall(tool_call_name)]))])


def _get_progress() -> dict:
    if hasattr(g, "th"):
        return g.th.getTopicProgress()
    return {"current": 0, "total": 0, "ratio": 0}


class ReplyHandler:
    """Processes a single reply in the interview chat loop.

    The handler does NOT trigger analysis or session-close side effects.
    The route orchestrator is responsible for post-actions.
    """

    def __init__(self, topic_handler):
        """
        Parameters
        ----------
        topic_handler : topicHandler
            The topic handler instance (currently ``g.th``).
        """
        self.th = topic_handler
        self.chat = conversation(topic_handler)

    def process(self, reply_input: ReplyInput) -> ReplyResult:
        """Non-streaming reply: call LLM, store messages, return result."""
        response_text = strip_raw_tool_text(
            self.chat.provideResponse(reply_input.message)
        )
        return ReplyResult(
            response_text=response_text,
            topic_status=self.chat.retrieveTopicStatus(),
            defined_answers=self.chat.retrieveDefinedAnswers(),
            progress=_get_progress(),
            debug=_build_reply_debug(self.chat),
        )

    def process_stream(self, reply_input: ReplyInput) -> Iterator[Tuple[str, object]]:
        """Streaming reply: yields ``(event_type, payload)`` tuples.

        Event types:
        - ``("keepalive", None)`` -- SSE comment to prevent proxy timeout
        - ``("delta", str)`` -- incremental text chunk
        - ``("final", ReplyResult)`` -- terminal event with full result

        The caller is responsible for converting these into SSE wire format
        and for triggering post-actions based on the final ``ReplyResult``.
        """
        yield ("keepalive", None)

        prompt_type = self.th.getTopicType(g.topic)

        if prompt_type not in ("prompt", "auto"):
            response_text = self.chat.provideResponse(reply_input.message)
            yield ("final", ReplyResult(
                response_text=response_text,
                topic_status=self.chat.retrieveTopicStatus(),
                defined_answers=self.chat.retrieveDefinedAnswers(),
                progress=_get_progress(),
                debug=_build_reply_debug(self.chat),
            ))
            return

        base = getattr(g, 'baseTopic', getattr(g, 'topic', None))
        cur = getattr(g, 'topic', None)
        g.db.store_message(g.projectId, g.uuid, base, cur,
                           "user", reply_input.message,
                           reply_input.voice_input, reply_input.audio_tokens)

        if getattr(g, 'topicIsChanging', None) is not None:
            system_prompt = self.chat.retrieveTopic() + "\n \n" + self.chat.getDefaultPrompt()
            self.chat.DB.store_message(g.projectId, g.uuid, base, cur,
                                       "system", system_prompt)

        is_auto = prompt_type == "auto"
        messages = self.chat.buildModelMessages(with_tool_note=is_auto)
        llm = LLM(allow_responses=True)
        tools = TOOL_SPEC if is_auto else None

        if prompt_type == "auto":
            # gpt-5 + tools streaming can stall; use non-stream for reliability.
            result = self._handle_auto_non_stream(llm, messages, tools, reply_input)
            yield ("final", result)
            return

        # Streaming path for "prompt" type
        full = ""
        tool_call_names: list = []
        for kind, val in llm.streamResponse(messages, tools=tools):
            if kind == "delta":
                full += val
                yield ("delta", val)
            elif kind == "tool_call":
                try:
                    fn = (val.get("function") or {}).get("name")
                    if fn:
                        tool_call_names.append(fn)
                except Exception:
                    pass

        full = strip_reasoning_leak(full)

        base = getattr(g, 'baseTopic', getattr(g, 'topic', None))
        cur = getattr(g, 'topic', None)
        self.chat.DB.store_message(g.projectId, g.uuid, base, cur,
                                   "assistant", full)

        if prompt_type == "auto" and not tool_call_names and "interview_topic_over" in full:
            tool_call_names.append("interview_topic_over")
            logger.warning("Raw tool call text in streamed content without proper tool_calls; treating as tool call")

        if prompt_type == "auto" and tool_call_names:
            switched_result = self._try_topic_switch(tool_call_names[0])
            if switched_result:
                yield ("final", switched_result)
                return

        full = strip_raw_tool_text(full)
        yield ("final", ReplyResult(
            response_text=full,
            topic_status=self.chat.retrieveTopicStatus(),
            defined_answers=self.chat.retrieveDefinedAnswers(),
            progress=_get_progress(),
            debug=_build_reply_debug(self.chat),
        ))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_auto_non_stream(self, llm, messages, tools, reply_input: ReplyInput) -> ReplyResult:
        """Handle auto-topic type via non-streaming LLM call."""
        response = llm.getResponse(messages, tools=tools)
        assistant_msg = response.choices[0].message
        full = strip_reasoning_leak(assistant_msg.content or "")

        tool_call_names = self._extract_tool_call_names(assistant_msg, full)

        if tool_call_names:
            switched_result = self._try_topic_switch(tool_call_names[0])
            if switched_result:
                return switched_result

        full = strip_raw_tool_text(full)
        base = getattr(g, 'baseTopic', getattr(g, 'topic', None))
        cur = getattr(g, 'topic', None)
        self.chat.DB.store_message(g.projectId, g.uuid, base, cur,
                                   "assistant", full)
        return ReplyResult(
            response_text=full,
            topic_status=self.chat.retrieveTopicStatus(),
            defined_answers=self.chat.retrieveDefinedAnswers(),
            progress=_get_progress(),
            debug=_build_reply_debug(self.chat),
        )

    @staticmethod
    def _extract_tool_call_names(assistant_msg, content: str) -> list:
        tool_call_names = []
        tool_calls = getattr(assistant_msg, "tool_calls", None) or []
        for tc in tool_calls:
            fn = None
            function_obj = getattr(tc, "function", None)
            if function_obj is not None:
                fn = getattr(function_obj, "name", None)
            if not fn and isinstance(tc, dict):
                fn = (tc.get("function") or {}).get("name")
            if fn:
                tool_call_names.append(fn)

        if not tool_call_names and "interview_topic_over" in content:
            tool_call_names.append("interview_topic_over")
            logger.warning("Raw tool call text detected in content without proper tool_calls; treating as tool call")

        return tool_call_names

    def _try_topic_switch(self, tool_call_name: str) -> Optional[ReplyResult]:
        """Attempt a topic switch via autoTopic. Returns ReplyResult on success, None otherwise."""
        fake = _build_fake_tool_response(tool_call_name)
        new_topic_id = handle_tool_call(fake, topic_engine=self.th)
        if not new_topic_id:
            return None
        next_text = strip_raw_tool_text(self.chat.provideInitialResponse())
        return ReplyResult(
            response_text=next_text,
            topic_status=self.chat.retrieveTopicStatus(),
            defined_answers=self.chat.retrieveDefinedAnswers(),
            progress=_get_progress(),
            debug=_build_reply_debug(self.chat),
            topic_switched=True,
            new_topic_id=new_topic_id,
        )
