"""
Regression tests for the auto-topic infinite loop (March 2026).

Root cause: when gpt-4.1 called interview_topic_over on an initial response
(before any user message), three bugs combined into an infinite recursion:

  1. forceSwitchTopic never updated self.topic — recursive calls kept
     resolving the same "next" topic, looping forever on one topic.
  2. forceSwitchTopic returned g.topic (truthy) when no next topic existed,
     so the last topic triggered infinite recursion too.
  3. provideInitialResponse passed tools to the LLM, letting the model
     call interview_topic_over before the user answered — triggering the
     recursive chain.

Each test below guards against one regression path.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import interview.conversation as ci
import autoTopic
from topic import topicHandler


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _DBStub:
    def __init__(self, records=None, topics=None, topics_log=None):
        self.records = list(records or [])
        self.topics = list(topics or [])
        self.topics_log = list(topics_log or [])
        self.inserts = []

    def query_database_all(self, query, params):
        if "FROM records" in query:
            return list(self.records)
        if "FROM topics_log" in query:
            return list(self.topics_log)
        if "FROM topics" in query:
            return list(self.topics)
        return []

    def query_database_one(self, query, params):
        if "SELECT defined_answers" in query:
            return (None,)
        if "SELECT default_prompt" in query:
            return ("DEFAULT PROMPT",)
        if "SELECT expiration_strategy" in query:
            return (None,)
        if "SELECT topic_type" in query:
            return ("auto",)
        if "select count" in query.lower():
            return (0,)
        return (None,)

    def query_database_insert(self, query, params):
        self.inserts.append((query, params))

    def store_message(self, project_id, user_id, base_topic, current_topic,
                      role, content, voice_input=False, audio_tokens=0):
        topic = base_topic if role == "user" else current_topic
        self.records.append((datetime.now(timezone.utc), role, content, topic))

    def close(self):
        pass


class _TopicStub:
    def __init__(self, topic_type="auto"):
        self.topic_type = topic_type

    def findTopicById(self, topic_id):
        return (1, topic_id, f"CURRENT TOPIC: question for {topic_id}", 1)

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, datetime.now(timezone.utc), 1, 0)

    def getTopicType(self, topic_id):
        return self.topic_type


class _ResponseMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _ToolFunctionStub:
    def __init__(self, name):
        self.name = name


class _ToolCallStub:
    def __init__(self, name="interview_topic_over"):
        self.function = _ToolFunctionStub(name)


class _ResponseChoice:
    def __init__(self, message):
        self.message = message


class _ResponseStub:
    def __init__(self, content, tool_calls=None):
        self.choices = [_ResponseChoice(_ResponseMessage(content, tool_calls))]


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


# ---------------------------------------------------------------------------
# 1. forceSwitchTopic must update self.topic
# ---------------------------------------------------------------------------

def test_force_switch_topic_updates_self_topic(app_ctx):
    """After forceSwitchTopic, self.topic must point to the NEW topic,
    not the old one. A stale self.topic caused the infinite loop."""
    topics_rows = [
        ("t01", "CURRENT TOPIC: q1", 1),
        ("t02", "CURRENT TOPIC: q2", 1),
        ("t03", "CURRENT TOPIC: q3", 1),
    ]
    topics_log_rows = [
        (1, 1, "t01", datetime.now(timezone.utc), 1, 0),
    ]
    db = _DBStub(topics=topics_rows, topics_log=topics_log_rows)

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"

    th = topicHandler.__new__(topicHandler)
    th.project = "test_proj"
    th.uuid = "test-user"
    th.DB = db
    th.topics = [
        (1, "t01", "CURRENT TOPIC: q1", 1),
        (2, "t02", "CURRENT TOPIC: q2", 1),
        (3, "t03", "CURRENT TOPIC: q3", 1),
    ]
    th.topic = "t01"
    g.th = th

    result = th.forceSwitchTopic()
    assert result == "t02"
    assert th.topic == "t02", "self.topic must be updated to the new topic"

    result2 = th.forceSwitchTopic()
    assert result2 == "t03"
    assert th.topic == "t03", "second call must advance to t03, not loop on t02"


def test_force_switch_consecutive_calls_never_repeat(app_ctx):
    """Calling forceSwitchTopic N times must visit N distinct topics
    in order, never repeating. This is the core infinite-loop guard."""
    topic_ids = [f"t{i:02d}" for i in range(1, 8)]
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = topic_ids[0]

    th = topicHandler.__new__(topicHandler)
    th.project = "test_proj"
    th.uuid = "test-user"
    th.DB = db
    th.topics = [(i + 1, tid, f"CURRENT TOPIC: q{i+1}", 1) for i, tid in enumerate(topic_ids)]
    th.topic = topic_ids[0]
    g.th = th

    visited = []
    for _ in range(len(topic_ids) + 5):
        result = th.forceSwitchTopic()
        if result is None:
            break
        visited.append(result)

    assert visited == topic_ids[1:], (
        f"Must visit topics in order without repeats: expected {topic_ids[1:]}, got {visited}"
    )


# ---------------------------------------------------------------------------
# 2. forceSwitchTopic must return None on the last topic
# ---------------------------------------------------------------------------

def test_force_switch_last_topic_returns_none(app_ctx):
    """When there is no next topic, forceSwitchTopic must return None
    (falsy) so callers don't recurse into provideInitialResponse."""
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t_last"

    th = topicHandler.__new__(topicHandler)
    th.project = "test_proj"
    th.uuid = "test-user"
    th.DB = db
    th.topics = [
        (1, "t_last", "CURRENT TOPIC: final question", 1),
    ]
    th.topic = "t_last"
    g.th = th

    result = th.forceSwitchTopic()
    assert result is None, (
        "forceSwitchTopic must return None when no next topic exists; "
        "returning a truthy value causes infinite recursion"
    )


def test_autotopic_switch_returns_none_on_last_topic(app_ctx):
    """autoTopic.switchTopic must return a falsy value on the last topic,
    so the streaming handler and provideResponse don't enter the
    topic-switch branch."""
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t_only"

    th = topicHandler.__new__(topicHandler)
    th.project = "test_proj"
    th.uuid = "test-user"
    th.DB = db
    th.topics = [(1, "t_only", "CURRENT TOPIC: sole question", 1)]
    th.topic = "t_only"
    g.th = th

    fake_response = _ResponseStub("", [_ToolCallStub("interview_topic_over")])
    result = autoTopic.switchTopic(fake_response)
    assert not result, (
        "switchTopic must return falsy on the last topic to prevent recursion"
    )


# ---------------------------------------------------------------------------
# 3. provideInitialResponse must never pass tools (no tool calls possible)
# ---------------------------------------------------------------------------

class _LLMSingleCall:
    """Records every call. provideInitialResponse should make exactly one
    call with no tools."""
    call_count = 0
    calls = []

    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMSingleCall.call_count += 1
        _LLMSingleCall.calls.append({"tools": tools})
        return _ResponseStub("When you open SweepKing, what's your goal?")


def test_initial_response_never_passes_tools(app_ctx, monkeypatch):
    """provideInitialResponse must never pass tools to the LLM — the opening
    question for a new topic has no reason to offer interview_topic_over."""
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "t02"
    g.baseTopic = "t02"
    g.topicIsChanging = True
    g.db = db

    _LLMSingleCall.call_count = 0
    _LLMSingleCall.calls = []
    monkeypatch.setattr(ci, "LLM", _LLMSingleCall)

    chat = ci.conversation(_TopicStub(topic_type="auto"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"
    result = chat.provideInitialResponse()

    assert result == "When you open SweepKing, what's your goal?"
    assert _LLMSingleCall.call_count == 1, (
        "Must call LLM exactly once (no tools, no retry)"
    )
    assert _LLMSingleCall.calls[0]["tools"] is None, (
        "provideInitialResponse must NOT pass tools"
    )


def test_initial_response_single_llm_call(app_ctx, monkeypatch):
    """provideInitialResponse must make exactly one LLM call. No retries,
    no tool-call detection loop — tools are never passed."""

    class _LLMCounter:
        call_count = 0
        def __init__(self, *a, **kw):
            pass
        def getResponse(self, messages, tools=None, tool_choice=None):
            _LLMCounter.call_count += 1
            if _LLMCounter.call_count > 10:
                pytest.fail("Infinite loop detected: LLM called more than 10 times")
            return _ResponseStub("Fallback question text")

    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "t01"
    g.baseTopic = "t01"
    g.topicIsChanging = True
    g.db = db

    _LLMCounter.call_count = 0
    monkeypatch.setattr(ci, "LLM", _LLMCounter)

    chat = ci.conversation(_TopicStub(topic_type="auto"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"
    result = chat.provideInitialResponse()

    assert result == "Fallback question text"
    assert _LLMCounter.call_count == 1, "Must call LLM exactly 1 time, not loop"


def test_initial_response_strips_raw_tool_call_text(app_ctx, monkeypatch):
    """If the model emits raw interview_topic_over(...) text (even without
    tools being passed), the safety-net strip must remove it."""

    class _LLMToolTextLeak:
        def __init__(self, *a, **kw):
            pass

        def getResponse(self, messages, tools=None, tool_choice=None):
            return _ResponseStub(
                'interview_topic_over({"status":"done"}) What role do free sweep coins play for you?'
            )

    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "t01"
    g.baseTopic = "t01"
    g.topicIsChanging = True
    g.db = db

    monkeypatch.setattr(ci, "LLM", _LLMToolTextLeak)

    chat = ci.conversation(_TopicStub(topic_type="auto"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"
    result = chat.provideInitialResponse()

    assert "interview_topic_over" not in result, (
        "Raw tool call text must never be shown to the user"
    )
    assert result == "What role do free sweep coins play for you?"

    stored_assistant_msgs = [
        content for (_, role, content, _) in db.records if role == "assistant"
    ]
    for msg in stored_assistant_msgs:
        assert "interview_topic_over" not in (msg or ""), (
            "Raw tool call text must never be stored in DB records"
        )


# ---------------------------------------------------------------------------
# 4. Full chain: provideResponse → forceSwitchTopic → provideInitialResponse
# ---------------------------------------------------------------------------

class _LLMChainStub:
    """Simulates the full chain: first call returns tool call (topic done),
    subsequent calls return text questions."""
    call_count = 0

    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMChainStub.call_count += 1
        if _LLMChainStub.call_count > 20:
            pytest.fail("Infinite loop: more than 20 LLM calls in one request")
        if tools and _LLMChainStub.call_count == 1:
            return _ResponseStub("", [_ToolCallStub()])
        return _ResponseStub(f"Question #{_LLMChainStub.call_count}")


def test_provide_response_auto_topic_switch_no_infinite_loop(app_ctx, monkeypatch):
    """End-to-end: provideResponse handles a tool call, switches topic,
    calls provideInitialResponse, and returns — within bounded LLM calls."""
    records = [
        (datetime.now(timezone.utc), "assistant", "Have you tried purchasing?", "t01"),
        (datetime.now(timezone.utc), "user", "no", "t01"),
    ]
    db = _DBStub(records=records)

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "t01"
    g.baseTopic = "t01"
    g.topicIsChanging = None
    g.db = db
    g.response_count = 1

    topic_stub = _TopicStub(topic_type="auto")
    topic_stub.findTopicById = lambda tid: (
        1 if tid == "t01" else 2,
        tid,
        f"CURRENT TOPIC: question for {tid}",
        1,
    )
    g.th = topic_stub

    _LLMChainStub.call_count = 0
    monkeypatch.setattr(ci, "LLM", _LLMChainStub)

    def mock_force_switch():
        g.topic = "t02"
        g.topicIsChanging = True
        return "t02"

    mock_switch = lambda resp, topic_engine=None: mock_force_switch() \
        if getattr(resp.choices[0].message, "tool_calls", None) else None
    monkeypatch.setattr(autoTopic, "switchTopic", mock_switch)
    import interview.topic_engine as _te
    monkeypatch.setattr(_te, "handle_tool_call", mock_switch)

    chat = ci.conversation(topic_stub)
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"

    result = chat.provideResponse("I dont have crypto")

    assert result is not None
    assert "interview_topic_over" not in (result or ""), "Raw tool text must not leak"
    assert _LLMChainStub.call_count <= 5, (
        f"Too many LLM calls ({_LLMChainStub.call_count}), possible loop"
    )


# ---------------------------------------------------------------------------
# 5. changeLogEntryStatus must scope to current user only
# ---------------------------------------------------------------------------

def test_change_log_entry_status_scoped_to_user(app_ctx):
    """changeLogEntryStatus must only close the *current user's* topic entry,
    not all users' entries for the same topic_id. The old query was:
      UPDATE topics_log SET status=0 WHERE topic_id=%s
    which closed every user's entry, causing cross-user contamination."""
    topics_rows = [
        ("t01", "CURRENT TOPIC: q1", 1),
        ("t02", "CURRENT TOPIC: q2", 1),
    ]
    db = _DBStub(topics=topics_rows)

    g.projectId = "test_proj"
    g.uuid = "user-A"
    g.db = db

    th = topicHandler.__new__(topicHandler)
    th.project = "test_proj"
    th.uuid = "user-A"
    th.DB = db
    th.topics = [
        (1, "t01", "CURRENT TOPIC: q1", 1),
        (2, "t02", "CURRENT TOPIC: q2", 1),
    ]
    th.topic = "t01"

    th.changeLogEntryStatus()

    assert len(db.inserts) == 1
    query, params = db.inserts[0]
    assert "user_id" in query.lower(), (
        "UPDATE query must include a user_id filter to avoid cross-user contamination"
    )
    assert params == ("t01", "user-A"), (
        f"Params must include both topic_id and user_id, got {params}"
    )
