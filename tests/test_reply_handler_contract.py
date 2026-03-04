"""Contract tests for ReplyHandler (interview/reply_handler.py).

Verifies the module boundary: ReplyHandler receives a ReplyInput, produces a
ReplyResult, and never calls AnalysisService on its own.  All LLM / DB /
topic-engine interactions are stubbed.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import interview.reply_handler as rh
import interview.topic_engine as te
from interview.types import ReplyInput, ReplyResult


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _DBStub:
    def __init__(self, records=None):
        self.records = list(records or [])
        self.messages = []

    def query_database_all(self, query, params):
        if "FROM records" in query:
            return list(self.records)
        if "FROM topics" in query:
            return []
        if "FROM topics_log" in query:
            return []
        return []

    def query_database_one(self, query, params):
        if "SELECT defined_answers" in query:
            return (None,)
        if "SELECT default_prompt" in query:
            return ("DEFAULT PROMPT",)
        if "SELECT topic_type" in query:
            return ("prompt",)
        if "SELECT expiration_strategy" in query:
            return (None,)
        if "SELECT external_id" in query:
            return ("user@test.com",)
        if "SELECT model" in query:
            return ("gpt-5", "medium")
        if "select count" in query.lower():
            return (0,)
        return (None,)

    def store_message(self, project_id, user_id, base_topic, current_topic,
                      role, content, voice_input=False, audio_tokens=0):
        topic = base_topic if role == "user" else current_topic
        self.messages.append((role, content))
        self.records.append((datetime.now(timezone.utc), role, content, topic))

    def query_database_insert(self, query, params):
        pass

    def close(self):
        pass


class _TopicHandlerStub:
    def __init__(self, topic_type="prompt", progress=None):
        self.topic_type = topic_type
        self._progress = progress or {"current": 2, "total": 5, "ratio": 0.4}
        self.findTopicById_calls = []

    def getTopicType(self, topic):
        return self.topic_type

    def getTopicProgress(self):
        return dict(self._progress)

    def findTopicById(self, topic_id):
        self.findTopicById_calls.append(topic_id)
        return (1, topic_id, f"CURRENT TOPIC: question for {topic_id}", 1)

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, datetime.now(timezone.utc), 1, 0)


class _ResponseMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _ResponseChoice:
    def __init__(self, message):
        self.message = message


class _ResponseStub:
    def __init__(self, content, tool_calls=None):
        self.choices = [_ResponseChoice(_ResponseMessage(content, tool_calls))]


class _ConversationStub:
    """Tracks calls for assertion without hitting real DB/LLM."""
    def __init__(self, _th):
        self.DB = g.db
        self.provide_response_calls = []
        self.provide_initial_calls = 0

    def provideResponse(self, user_input):
        self.provide_response_calls.append(user_input)
        return "Assistant says hello"

    def provideInitialResponse(self):
        self.provide_initial_calls += 1
        return "Welcome to the next topic"

    def buildModelMessages(self):
        return [{"role": "system", "content": "CURRENT TOPIC: test question"}]

    def retrieveTopicStatus(self):
        return "open"

    def retrieveDefinedAnswers(self):
        return None

    def retrieveTopic(self):
        return "CURRENT TOPIC: test question"

    def getDefaultPrompt(self, topic_id=None):
        return "DEFAULT PROMPT"

    def _get_topic_meta(self, topic_id):
        return {"title": "Test topic", "id": topic_id}


class _LLMStub:
    calls = []

    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMStub.calls.append({"messages": messages, "tools": tools})
        return _ResponseStub("LLM response text")

    def streamResponseOpenAI(self, messages, tools=None):
        yield ("delta", "Hello ")
        yield ("delta", "world")


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


@pytest.fixture
def seeded_ctx(app_ctx):
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "test_topic_01"
    g.baseTopic = "test_topic_01"
    g.topicIsChanging = None
    g.db = db
    g.response_count = 0
    return db


# ---------------------------------------------------------------------------
# 6A-1: process() creates messages via conversation, returns ReplyResult
# ---------------------------------------------------------------------------

def test_reply_process_returns_reply_result(seeded_ctx, monkeypatch):
    """process() must return a well-formed ReplyResult."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub()
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="Hello there")

    result = handler.process(inp)

    assert isinstance(result, ReplyResult)
    assert result.response_text == "Assistant says hello"
    assert result.topic_status == "open"
    assert result.progress == {"current": 2, "total": 5, "ratio": 0.4}


def test_reply_process_passes_message_to_conversation(seeded_ctx, monkeypatch):
    """process() must forward the user message to conversation.provideResponse()."""
    stub = None

    class _TrackingConversation(_ConversationStub):
        def __init__(self, _th):
            nonlocal stub
            super().__init__(_th)
            stub = self

    monkeypatch.setattr(rh, "conversation", _TrackingConversation)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub()
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="I play every day")

    handler.process(inp)
    assert stub.provide_response_calls == ["I play every day"]


# ---------------------------------------------------------------------------
# 6A-2: process() never calls AnalysisService
# ---------------------------------------------------------------------------

def test_reply_process_does_not_trigger_analysis(seeded_ctx, monkeypatch):
    """ReplyHandler must never import or call AnalysisService.
    Analysis is the orchestrator's responsibility."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub()
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="test")

    handler.process(inp)

    source = Path(rh.__file__).read_text(encoding="utf-8")
    assert "AnalysisService" not in source, (
        "ReplyHandler must not reference AnalysisService — analysis is a post-action"
    )


# ---------------------------------------------------------------------------
# 6A-3: process_stream yields keepalive, delta, final in order
# ---------------------------------------------------------------------------

def test_reply_stream_yields_keepalive_first(seeded_ctx, monkeypatch):
    """Streaming must emit keepalive as the very first event."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub(topic_type="prompt")
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="hi", wants_stream=True)

    events = list(handler.process_stream(inp))
    assert events[0][0] == "keepalive", "First event must be keepalive"


def test_reply_stream_ends_with_final(seeded_ctx, monkeypatch):
    """Streaming must always end with a final event containing ReplyResult."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub(topic_type="prompt")
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="hi", wants_stream=True)

    events = list(handler.process_stream(inp))
    last_type, last_data = events[-1]
    assert last_type == "final"
    assert isinstance(last_data, ReplyResult)
    assert last_data.topic_status == "open"


def test_reply_stream_prompt_emits_deltas(seeded_ctx, monkeypatch):
    """Prompt-type streaming must emit delta events from LLM chunks."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    th = _TopicHandlerStub(topic_type="prompt")
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="tell me more", wants_stream=True)

    events = list(handler.process_stream(inp))
    deltas = [e for e in events if e[0] == "delta"]
    assert len(deltas) >= 1, "Prompt streaming must emit at least one delta"


# ---------------------------------------------------------------------------
# 6A-4: progress reflects topic state
# ---------------------------------------------------------------------------

def test_reply_returns_progress_from_topic_handler(seeded_ctx, monkeypatch):
    """Progress in ReplyResult must come from topic_handler.getTopicProgress()."""
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    custom_progress = {"current": 7, "total": 11, "ratio": 7 / 11}
    th = _TopicHandlerStub(progress=custom_progress)
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="ok")

    result = handler.process(inp)
    assert result.progress["current"] == 7
    assert result.progress["total"] == 11
    assert abs(result.progress["ratio"] - 7 / 11) < 0.01


# ---------------------------------------------------------------------------
# 6A-5: topic switch via auto path
# ---------------------------------------------------------------------------

class _ToolFunctionStub:
    def __init__(self, name):
        self.name = name


class _ToolCallStub:
    def __init__(self, name="interview_topic_over"):
        self.function = _ToolFunctionStub(name)


class _LLMAutoToolStub:
    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        return _ResponseStub("", [_ToolCallStub("interview_topic_over")])


class _ConversationAutoStub(_ConversationStub):
    def provideInitialResponse(self):
        return "Next topic opening question"


def test_reply_auto_topic_switch_sets_topic_switched_flag(seeded_ctx, monkeypatch):
    """When auto-topic switch occurs, ReplyResult.topic_switched must be True."""
    monkeypatch.setattr(rh, "conversation", _ConversationAutoStub)
    monkeypatch.setattr(rh, "LLM", _LLMAutoToolStub)
    mock_switch = lambda response, topic_engine=None: "test_topic_02"
    monkeypatch.setattr(te, "handle_tool_call", mock_switch)
    monkeypatch.setattr(rh, "handle_tool_call", mock_switch)

    th = _TopicHandlerStub(topic_type="auto")
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="done with this")

    events = list(handler.process_stream(inp))
    final_events = [e for e in events if e[0] == "final"]
    assert len(final_events) == 1
    result = final_events[0][1]
    assert result.topic_switched is True
    assert result.response_text == "Next topic opening question"


def test_reply_auto_no_switch_when_no_tool_call(seeded_ctx, monkeypatch):
    """When auto-topic LLM returns text without tool call, no switch occurs."""

    class _LLMNoTool:
        def __init__(self, *a, **kw): pass
        def getResponse(self, messages, tools=None, tool_choice=None):
            return _ResponseStub("Just a regular response")

    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMNoTool)

    th = _TopicHandlerStub(topic_type="auto")
    g.th = th
    handler = ReplyHandler(th)
    inp = ReplyInput(message="tell me more")

    events = list(handler.process_stream(inp))
    final_events = [e for e in events if e[0] == "final"]
    assert len(final_events) == 1
    result = final_events[0][1]
    assert result.topic_switched is False


# ---------------------------------------------------------------------------
# 6A-6: ReplyResult.to_dict produces valid response shape
# ---------------------------------------------------------------------------

def test_reply_result_to_dict_includes_required_fields():
    """to_dict() must include response, status, answers, progress, version."""
    result = ReplyResult(
        response_text="Hello",
        topic_status="open",
        defined_answers="option A;option B",
        progress={"current": 1, "total": 3, "ratio": 0.33},
    )
    d = result.to_dict("abc1234")
    assert d["response"] == "Hello"
    assert d["status"] == "open"
    assert d["answers"] == "option A;option B"
    assert d["progress"]["current"] == 1
    assert d["version"] == "abc1234"
    assert "_debug" not in d


def test_reply_result_to_dict_includes_debug_when_set():
    """to_dict() must include _debug only when debug is set."""
    result = ReplyResult(
        response_text="Hi",
        topic_status="open",
        debug={"model": "gpt-5", "topic_title": "Test"},
    )
    d = result.to_dict("v1")
    assert "_debug" in d
    assert d["_debug"]["model"] == "gpt-5"


# Ensure we import ReplyHandler from the module
from interview.reply_handler import ReplyHandler
