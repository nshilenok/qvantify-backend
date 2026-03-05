"""Tests for idempotent interview initialization.

Covers two layers of protection against duplicate GET /api/interview/ calls:

Layer 1 — Endpoint guard in initialize_interview() (server.py):
    If assistant records already exist, return the last one without calling LLM.

Layer 2 — Method guard in provideInitialResponse() (conversation.py):
    If topic is NOT changing and assistant records exist, return cached.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server as srv
import interview.conversation as ci


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

_TS = datetime(2026, 3, 5, 6, 22, 20, tzinfo=timezone.utc)


class _DBStub:
    def __init__(self, records=None, topics=None, topics_log=None):
        self.records = list(records or [])
        self._topics = list(topics or [])
        self._topics_log = list(topics_log or [])
        self.inserts = []
        self._respondent = None
        self._topic_type = "auto"
        self._topic_log_status = 1

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
            return (self._topic_type,)
        if "SELECT external_id" in query:
            return ("ext-123",)
        if "SELECT model" in query:
            return ("gpt-5", "medium")
        if "select count" in query.lower():
            return (0,)
        if 'SELECT id, title, system, "group", sequence' in query:
            return ("t01", "Test Topic", "CURRENT TOPIC: test", "grp", 1)
        if "SELECT" in query and '"group"' in query and "sequence >" in query:
            return []
        return (None,)

    def query_database_insert(self, query, params):
        self.inserts.append((query, params))

    def query_dict_one(self, query, params):
        return None

    def query_dict_all(self, query, params):
        return []

    def get_records(self, uuid, project):
        rows = self.query_database_all(
            "SELECT created_at,role,content,topic FROM records WHERE user_id=%s AND project=%s ORDER by created_at ASC",
            (uuid, project),
        )
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def store_message(self, project_id, user_id, base_topic, current_topic,
                      role, content, voice_input=False, audio_tokens=0):
        topic = base_topic if role == "user" else current_topic
        self.records.append((datetime.now(timezone.utc), role, content, topic))

    def close(self):
        pass


class _TopicHandlerStub:
    def __init__(self, topic_type="auto"):
        self.topic_type = topic_type
        self._progress = {"current": 1, "total": 3, "ratio": 1 / 3}
        self._topic_log_status = 1

    def getTopicType(self, topic):
        return self.topic_type

    def getTopicProgress(self):
        return dict(self._progress)

    def findTopicById(self, topic_id):
        return (1, topic_id, f"CURRENT TOPIC: question for {topic_id}", 1)

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, _TS, self._topic_log_status, 0)

    def getTopicsLog(self):
        return [(1, 1, "t01", _TS, 1, 0)]

    def getCurrentTopic(self):
        return "t01"

    def switchTopic(self, response_count=None):
        return ("t01", False)

    def updateResponseCounter(self, base_topic=None, user_id=None):
        return (1,)

    def forceSwitchTopic(self):
        return None


class _ClosedTopicHandlerStub(_TopicHandlerStub):
    def __init__(self):
        super().__init__()
        self._topic_log_status = 0

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, _TS, 0, 2)


class _ConversationStub:
    init_calls = 0

    def __init__(self, _th):
        _ConversationStub.init_calls = 0
        self.DB = g.db

    def provideResponse(self, user_input):
        return "The assistant responds here"

    def provideInitialResponse(self):
        _ConversationStub.init_calls += 1
        return "Welcome to the interview"

    def buildModelMessages(self, with_tool_note=False):
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
    calls = 0

    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMStub.calls += 1
        return _ResponseStub("Fresh LLM response")


def _seed_request_context(db, monkeypatch, *, conversation_cls=_ConversationStub):
    db._respondent = ("test-user", "test_proj")
    monkeypatch.setattr(srv, "check_if_user_exists", lambda: None)
    monkeypatch.setattr(srv, "conversation", conversation_cls)

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.topic = "t01"
    g.baseTopic = "t01"
    g.th = _TopicHandlerStub()
    g.db = db
    g.response_count = 0
    g.llm_purpose = "chat"
    g.llm_service = "core"


# ---------------------------------------------------------------------------
# Layer 1 — Endpoint guard tests
# ---------------------------------------------------------------------------

def test_first_init_calls_provideInitialResponse(monkeypatch):
    """First-ever init (no records) must call provideInitialResponse normally."""
    db = _DBStub()
    with srv.app.test_request_context(
        "/api/interview/",
        method="GET",
        headers={"projectId": "test_proj", "uuid": "test-user"},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.initialize_interview()

        data = response.get_json() if not isinstance(response, tuple) else response[0].get_json()
        assert data["response"] == "Welcome to the interview"
        assert data["status"] == "open"
        assert "progress" in data
        assert _ConversationStub.init_calls == 1


def test_duplicate_init_returns_cached_without_llm(monkeypatch):
    """When assistant records exist, return cached response without calling LLM."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: question", "t01"),
        (_TS, "assistant", "Have you ever tried to make a purchase?", "t01"),
    ])
    with srv.app.test_request_context(
        "/api/interview/",
        method="GET",
        headers={"projectId": "test_proj", "uuid": "test-user"},
    ):
        _seed_request_context(db, monkeypatch)
        initial_record_count = len(db.records)
        response = srv.initialize_interview()

        data = response.get_json() if not isinstance(response, tuple) else response[0].get_json()
        assert data["response"] == "Have you ever tried to make a purchase?"
        assert data["status"] == "open"
        assert _ConversationStub.init_calls == 0, "provideInitialResponse must NOT be called"
        assert len(db.records) == initial_record_count, "No new records should be stored"


def test_resume_mid_interview_returns_last_assistant(monkeypatch):
    """Resume mid-interview returns the last assistant message (latest question)."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: q1", "t01"),
        (_TS, "assistant", "What is your name?", "t01"),
        (_TS, "user", "John", "t01"),
        (_TS, "assistant", "How often do you play?", "t01"),
    ])
    with srv.app.test_request_context(
        "/api/interview/",
        method="GET",
        headers={"projectId": "test_proj", "uuid": "test-user"},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.initialize_interview()

        data = response.get_json() if not isinstance(response, tuple) else response[0].get_json()
        assert data["response"] == "How often do you play?"
        assert _ConversationStub.init_calls == 0


def test_resume_after_closed_returns_closed_status(monkeypatch):
    """Resume after interview closed returns last message with status=closed."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: q1", "t01"),
        (_TS, "assistant", "Thank you for your time!", "t01"),
    ])
    with srv.app.test_request_context(
        "/api/interview/",
        method="GET",
        headers={"projectId": "test_proj", "uuid": "test-user"},
    ):
        _seed_request_context(db, monkeypatch, conversation_cls=_ClosedConversationStub)
        g.th = _ClosedTopicHandlerStub()
        response = srv.initialize_interview()

        data = response.get_json() if not isinstance(response, tuple) else response[0].get_json()
        assert data["response"] == "Thank you for your time!"
        assert data["status"] == "closed"


def test_partial_failure_reinitializes(monkeypatch):
    """If only a system record exists (no assistant), normal init must proceed."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: question", "t01"),
    ])
    with srv.app.test_request_context(
        "/api/interview/",
        method="GET",
        headers={"projectId": "test_proj", "uuid": "test-user"},
    ):
        _seed_request_context(db, monkeypatch)
        response = srv.initialize_interview()

        data = response.get_json() if not isinstance(response, tuple) else response[0].get_json()
        assert data["response"] == "Welcome to the interview"
        assert _ConversationStub.init_calls == 1, "provideInitialResponse must be called"


# ---------------------------------------------------------------------------
# Layer 2 — Method guard tests (provideInitialResponse)
# ---------------------------------------------------------------------------

@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


class _TopicStub:
    def __init__(self, topic_type="auto"):
        self.topic_type = topic_type

    def findTopicById(self, topic_id):
        return (1, topic_id, f"CURRENT TOPIC: question for {topic_id}", 1)

    def findTopicLogEntry(self, topic_id):
        return (1, 1, topic_id, _TS, 1, 0)

    def getTopicType(self, topic_id):
        return self.topic_type


def test_initial_response_no_topic_change_returns_cached(app_ctx, monkeypatch):
    """Without topic change, provideInitialResponse returns existing assistant message."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: q1", "t01"),
        (_TS, "assistant", "Cached question from before", "t01"),
    ])
    db._topic_type = "auto"

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"
    g.baseTopic = "t01"

    _LLMStub.calls = 0
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub("auto"), db=db, project_id="test_proj",
                           user_id="test-user", topic_id="t01", base_topic="t01")
    result = chat.provideInitialResponse()

    assert result == "Cached question from before"
    assert _LLMStub.calls == 0, "LLM must NOT be called"
    assert len(db.records) == 2, "No new records should be stored"


def test_initial_response_with_topic_change_generates_new(app_ctx, monkeypatch):
    """With topic change, provideInitialResponse generates a fresh response."""
    db = _DBStub(records=[
        (_TS, "system", "CURRENT TOPIC: q1", "t01"),
        (_TS, "assistant", "Old question", "t01"),
    ])
    db._topic_type = "auto"

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t02"
    g.baseTopic = "t01"
    g.topicIsChanging = True

    _LLMStub.calls = 0
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub("auto"), db=db, project_id="test_proj",
                           user_id="test-user", topic_id="t02", base_topic="t01")
    result = chat.provideInitialResponse()

    assert result == "Fresh LLM response"
    assert _LLMStub.calls == 1, "LLM must be called for new topic"
    assert len(db.records) > 2, "New records should be stored"


def test_initial_response_first_init_generates_new(app_ctx, monkeypatch):
    """First-time init (no records, topic changing) generates a fresh response."""
    db = _DBStub()
    db._topic_type = "auto"

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"
    g.baseTopic = "t01"
    g.topicIsChanging = True

    _LLMStub.calls = 0
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub("auto"), db=db, project_id="test_proj",
                           user_id="test-user", topic_id="t01", base_topic="t01")
    result = chat.provideInitialResponse()

    assert result == "Fresh LLM response"
    assert _LLMStub.calls == 1, "LLM must be called for first init"
    stored_roles = [r[1] for r in db.records]
    assert "system" in stored_roles, "System prompt should be stored"
    assert "assistant" in stored_roles, "Assistant response should be stored"
