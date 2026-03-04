"""Integration tests for the full /api/reply/ cascade.

Uses Flask test_request_context to exercise the route handler end-to-end,
verifying that DB records, usage, topics_log, and response JSON are correct.
All external dependencies (DB, LLM, user-check) are stubbed.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server as srv
import interview.reply_handler as rh
import interview.topic_engine as te
import interview.analysis as analysis_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drain_response_text(response):
    parts = []
    for chunk in response.response:
        if isinstance(chunk, bytes):
            parts.append(chunk.decode("utf-8"))
        else:
            parts.append(chunk)
    return "".join(parts)


def _extract_sse_payloads(body):
    payloads = []
    for event in body.split("\n\n"):
        for line in event.split("\n"):
            if line.startswith("data: "):
                payloads.append(json.loads(line[6:]))
    return payloads


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _DBStub:
    def __init__(self, records=None, topics=None, topics_log=None):
        self.records = list(records or [])
        self.messages = []
        self._topics = list(topics or [])
        self._topics_log = list(topics_log or [])
        self.inserts = []
        self._respondent = None

    def query_database_all(self, query, params):
        if "FROM records" in query:
            return list(self.records)
        if "FROM topics_log" in query:
            return list(self._topics_log)
        if "FROM topics" in query:
            return list(self._topics)
        return []

    def query_database_one(self, query, params):
        if "SELECT id,project FROM respondents" in query:
            return self._respondent
        if "SELECT defined_answers" in query:
            return (None,)
        if "SELECT default_prompt" in query:
            return ("DEFAULT PROMPT",)
        if "SELECT expiration_strategy" in query:
            return ("count",)
        if "SELECT topic_type" in query:
            return ("prompt",)
        if "SELECT external_id" in query:
            return ("user@test.com",)
        if "SELECT model" in query:
            return ("gpt-5", "medium")
        if "select count" in query.lower():
            return (0,)
        return (None,)

    def query_database_insert(self, query, params):
        self.inserts.append((query, params))

    def query_dict_one(self, query, params):
        return None

    def query_dict_all(self, query, params):
        return []

    def store_message(self, project_id, user_id, base_topic, current_topic,
                      role, content, voice_input=False, audio_tokens=0):
        self.messages.append((role, content))
        topic = base_topic if role == "user" else current_topic
        self.records.append((datetime.now(timezone.utc), role, content, topic))

    def close(self):
        pass


class _TopicHandlerStub:
    def __init__(self, topic_type="prompt"):
        self.topic_type = topic_type
        self._progress = {"current": 1, "total": 3, "ratio": 1 / 3}

    def getTopicType(self, topic):
        return self.topic_type

    def getTopicProgress(self):
        return dict(self._progress)

    def findTopicById(self, topic_id):
        return (1, topic_id, f"CURRENT TOPIC: question for {topic_id}", 1)

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, datetime.now(timezone.utc), 1, 0)

    def getTopicsLog(self):
        return [(1, 1, "t01", datetime.now(timezone.utc), 1, 0)]

    def getCurrentTopic(self):
        return "t01"

    def switchTopic(self, response_count=None):
        return ("t01", False)

    def updateResponseCounter(self, base_topic=None, user_id=None):
        return (1,)

    def forceSwitchTopic(self):
        return None


class _ConversationStub:
    def __init__(self, _th):
        self.DB = g.db

    def provideResponse(self, user_input):
        return "The assistant responds here"

    def provideInitialResponse(self):
        return "Welcome to the next topic"

    def buildModelMessages(self):
        return [{"role": "system", "content": "CURRENT TOPIC: test"}]

    def retrieveTopicStatus(self):
        return "open"

    def retrieveDefinedAnswers(self):
        return None

    def retrieveTopic(self):
        return "CURRENT TOPIC: test"

    def getDefaultPrompt(self, topic_id=None):
        return "DEFAULT"

    def _get_topic_meta(self, topic_id):
        return {"title": "Test", "id": topic_id}


class _ClosedConversationStub(_ConversationStub):
    def retrieveTopicStatus(self):
        return "closed"


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


class _LLMStub:
    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        return _ResponseStub("LLM response text")

    def streamResponseOpenAI(self, messages, tools=None):
        yield ("delta", "Hello")
        yield ("delta", " world")


def _seed_request_context(db, monkeypatch):
    """Monkey-patch all hooks so the route handler sees a valid context."""
    db._respondent = ("test-user", "test_proj")
    monkeypatch.setattr(srv, "check_if_user_exists", lambda: None)
    monkeypatch.setattr(rh, "conversation", _ConversationStub)
    monkeypatch.setattr(rh, "LLM", _LLMStub)

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "test_t01"
    g.baseTopic = "test_t01"
    g.topicIsChanging = None
    g.th = _TopicHandlerStub()
    g.db = db
    g.response_count = 1
    g.voice_input = False
    g.audio_tokens = 0
    g.llm_purpose = "chat"
    g.llm_service = "core"


# ---------------------------------------------------------------------------
# 6D-1: Non-streaming reply: verify response JSON matches ReplyResult schema
# ---------------------------------------------------------------------------

def test_full_reply_flow_non_streaming(monkeypatch):
    """POST /api/reply with non-streaming: verify response JSON shape."""
    db = _DBStub()
    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user"},
        json={"message": "I play every day"},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.gpt_response()

        if isinstance(response, tuple):
            resp_data, status = response
            data = resp_data.get_json()
        else:
            data = response.get_json()

        assert "response" in data, "Must include 'response' field"
        assert "status" in data, "Must include 'status' field"
        assert "progress" in data, "Must include 'progress' field"
        assert "version" in data, "Must include 'version' field"
        assert data["response"] == "The assistant responds here"
        assert data["status"] == "open"
        assert data["progress"]["current"] == 1
        assert data["progress"]["total"] == 3


# ---------------------------------------------------------------------------
# 6D-2: Non-streaming reply: analysis triggered on closed status
# ---------------------------------------------------------------------------

def test_non_streaming_triggers_analysis_on_closed(monkeypatch):
    """When topic status is 'closed', the orchestrator must call maybe_analyze."""
    analysis_calls = []

    class _TrackingAnalysis:
        def __init__(self, db, project_id):
            pass
        def maybe_analyze(self, respondent_id):
            analysis_calls.append(respondent_id)

    db = _DBStub()
    monkeypatch.setattr(srv, "AnalysisService", _TrackingAnalysis)

    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user"},
        json={"message": "goodbye"},
    ):
        _seed_request_context(db, monkeypatch)
        monkeypatch.setattr(rh, "conversation", _ClosedConversationStub)
        srv.gpt_response()

    assert "test-user" in analysis_calls, "must call maybe_analyze on closed status"


def test_non_streaming_skips_analysis_on_open(monkeypatch):
    """When topic status is 'open', analysis must NOT be called."""
    analysis_calls = []

    class _TrackingAnalysis:
        def __init__(self, db, project_id):
            pass
        def maybe_analyze(self, respondent_id):
            analysis_calls.append(respondent_id)

    db = _DBStub()
    monkeypatch.setattr(srv, "AnalysisService", _TrackingAnalysis)

    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user"},
        json={"message": "hello"},
    ):
        _seed_request_context(db, monkeypatch)
        srv.gpt_response()

    assert len(analysis_calls) == 0, "must NOT call maybe_analyze when status is open"


# ---------------------------------------------------------------------------
# 6D-3: Streaming reply: verify SSE shape
# ---------------------------------------------------------------------------

def test_streaming_reply_returns_sse_with_final(monkeypatch):
    """Streaming reply must return SSE with keepalive and final event."""
    db = _DBStub()
    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user", "Accept": "text/event-stream"},
        json={"message": "tell me more", "stream": True},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.gpt_response()

        assert response.status_code == 200
        body = _drain_response_text(response)
        assert body.startswith(":\n\n"), "Must start with SSE keepalive"

        payloads = _extract_sse_payloads(body)
        final = next((p for p in payloads if p.get("type") == "final"), None)
        assert final is not None, "Must end with final event"
        assert "response" in final
        assert "status" in final
        assert "version" in final
        assert "progress" in final


# ---------------------------------------------------------------------------
# 6D-4: Streaming with topic switch
# ---------------------------------------------------------------------------

class _ToolFunctionStub:
    def __init__(self, name):
        self.name = name


class _ToolCallStub:
    def __init__(self, name="interview_topic_over"):
        self.function = _ToolFunctionStub(name)


class _LLMAutoStub:
    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        return _ResponseStub("", [_ToolCallStub("interview_topic_over")])


class _TopicHandlerAutoStub(_TopicHandlerStub):
    def __init__(self):
        super().__init__(topic_type="auto")

    def forceSwitchTopic(self):
        self.topic = "test_t02"
        return "test_t02"


class _ConversationAutoStub(_ConversationStub):
    def provideInitialResponse(self):
        return "Welcome to topic 2"


def test_streaming_reply_with_topic_switch(monkeypatch):
    """Streaming with auto-topic: final event must contain the next topic's text."""
    db = _DBStub()
    monkeypatch.setattr(rh, "conversation", _ConversationAutoStub)
    monkeypatch.setattr(rh, "LLM", _LLMAutoStub)
    mock_switch = lambda response, topic_engine=None: "test_t02"
    monkeypatch.setattr(te, "handle_tool_call", mock_switch)
    monkeypatch.setattr(rh, "handle_tool_call", mock_switch)

    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user", "Accept": "text/event-stream"},
        json={"message": "I'm done with this topic", "stream": True},
    ):
        _seed_request_context(db, monkeypatch)
        monkeypatch.setattr(rh, "conversation", _ConversationAutoStub)
        monkeypatch.setattr(rh, "LLM", _LLMAutoStub)
        monkeypatch.setattr(rh, "handle_tool_call", mock_switch)
        g.th = _TopicHandlerAutoStub()

        response = srv.gpt_response()
        assert response.status_code == 200

        body = _drain_response_text(response)
        payloads = _extract_sse_payloads(body)
        final = next((p for p in payloads if p.get("type") == "final"), None)
        assert final is not None
        assert final["response"] == "Welcome to topic 2"


# ---------------------------------------------------------------------------
# 6D-5: Invalid request returns 400
# ---------------------------------------------------------------------------

def test_missing_message_returns_400(monkeypatch):
    """POST /api/reply without 'message' field must return 400."""
    db = _DBStub()
    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user"},
        json={"not_message": "oops"},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.gpt_response()

        if isinstance(response, tuple):
            _, status = response
            assert status == 400
        else:
            assert response.status_code == 400


# ---------------------------------------------------------------------------
# 6D-6: streaming analysis trigger on closed
# ---------------------------------------------------------------------------

def test_streaming_triggers_analysis_on_closed(monkeypatch):
    """When streaming ends with closed status, the orchestrator must call maybe_analyze."""
    analysis_calls = []

    class _TrackingAnalysis:
        def __init__(self, db, project_id):
            pass
        def maybe_analyze(self, respondent_id):
            analysis_calls.append(respondent_id)

    db = _DBStub()
    monkeypatch.setattr(srv, "AnalysisService", _TrackingAnalysis)

    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "test_proj", "uuid": "test-user", "Accept": "text/event-stream"},
        json={"message": "bye", "stream": True},
    ):
        _seed_request_context(db, monkeypatch)
        monkeypatch.setattr(rh, "conversation", _ClosedConversationStub)

        response = srv.gpt_response()
        _drain_response_text(response)

    assert "test-user" in analysis_calls, "must call maybe_analyze on closed in streaming path"
