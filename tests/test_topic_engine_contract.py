"""Contract tests for TopicEngine (interview/topic_engine.py).

Verifies: advance (switchTopic/forceSwitchTopic) returns correct values,
no global state mutation leaks, tool call handling dispatches correctly,
strip_raw_tool_text cleans model artefacts.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from interview.topic_engine import (
    TopicEngine,
    handle_tool_call,
    force_switch_from_text,
    strip_raw_tool_text,
    TOOL_SPEC,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _DBStub:
    def __init__(self, topics=None, topics_log=None):
        self.topics = list(topics or [])
        self.topics_log = list(topics_log or [])
        self.inserts = []

    def query_database_all(self, query, params):
        if "FROM topics" in query and "topics_log" not in query:
            return list(self.topics)
        if "FROM topics_log" in query:
            return list(self.topics_log)
        return []

    def query_database_one(self, query, params):
        if "SELECT expiration_strategy" in query:
            return ("count",)
        if "SELECT topic_type" in query:
            return ("auto",)
        if "select count" in query.lower():
            return (0,)
        return (None,)

    def query_database_insert(self, query, params):
        self.inserts.append((query, params))

    def store_message(self, *a, **kw):
        pass

    def close(self):
        pass


class _ToolFunctionStub:
    def __init__(self, name):
        self.name = name


class _ToolCallStub:
    def __init__(self, name="interview_topic_over"):
        self.function = _ToolFunctionStub(name)


class _ResponseMessage:
    def __init__(self, content, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _ResponseChoice:
    def __init__(self, message):
        self.message = message


class _ResponseStub:
    def __init__(self, content="", tool_calls=None):
        self.choices = [_ResponseChoice(_ResponseMessage(content, tool_calls))]


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


def _make_engine(db, topics, topics_log=None, current_topic=None):
    """Create a TopicEngine bypassing __init__'s g.* reads."""
    te = TopicEngine.__new__(TopicEngine)
    te.project = "test_proj"
    te.uuid = "test-user"
    te.DB = db
    te.topics = [(i + 1, tid, f"CURRENT TOPIC: q{i+1}", length)
                 for i, (tid, length) in enumerate(topics)]
    te.topic = current_topic or topics[0][0]
    return te


# ---------------------------------------------------------------------------
# 6C-1: advance returns next topic when expired (count strategy)
# ---------------------------------------------------------------------------

def test_switch_topic_advances_when_expired(app_ctx):
    """switchTopic() must return the next topic_id when the current topic
    is expired and more topics remain."""
    topics = [("t01", 1), ("t02", 1), ("t03", 1)]
    # DB rows are 5-element: (id, topic_id, started_at, status, responses)
    topics_log_db = [(1, "t01", datetime.now(timezone.utc), 1, 0)]

    class _PromptDB(_DBStub):
        def query_database_one(self, query, params):
            if "SELECT expiration_strategy" in query:
                return ("count",)
            if "SELECT topic_type" in query:
                return ("prompt",)
            if "select count" in query.lower():
                return (0,)
            return (None,)

    db = _PromptDB(
        topics=[("t01", "q1", 1), ("t02", "q2", 1), ("t03", "q3", 1)],
        topics_log=topics_log_db,
    )

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"
    g.response_count = 5

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te

    topic_id, is_changing = te.switchTopic(response_count=5)
    assert topic_id == "t02", "switchTopic must advance to t02 when t01 is expired"
    assert is_changing is True


def test_switch_topic_returns_current_when_not_expired(app_ctx):
    """switchTopic() must return the current topic when it hasn't expired."""
    topics = [("t01", 99), ("t02", 99)]

    class _CountDB(_DBStub):
        def query_database_one(self, query, params):
            if "SELECT expiration_strategy" in query:
                return ("count",)
            if "SELECT topic_type" in query:
                return ("prompt",)
            if "select count" in query.lower():
                return (0,)
            return (None,)

    # DB rows are 5-element: (id, topic_id, started_at, status, responses)
    db = _CountDB(
        topics=[("t01", "q1", 99), ("t02", "q2", 99)],
        topics_log=[(1, "t01", datetime.now(timezone.utc), 1, 0)],
    )

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"
    g.response_count = 0

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te
    topic_id, is_changing = te.switchTopic(response_count=0)
    assert topic_id == "t01", "switchTopic must stay on t01 when not expired"
    assert is_changing is False


# ---------------------------------------------------------------------------
# 6C-2: forceSwitchTopic does not mutate global state beyond g.topic
# ---------------------------------------------------------------------------

def test_force_switch_returns_new_topic_and_updates_self(app_ctx):
    """forceSwitchTopic must return the new topic_id and update self.topic.
    It does NOT mutate g.topic or g.topicIsChanging directly."""
    topics = [("t01", 1), ("t02", 1), ("t03", 1)]
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te

    result = te.forceSwitchTopic()
    assert result == "t02"
    assert te.topic == "t02", "self.topic must be updated"


def test_force_switch_does_not_modify_unrelated_g_attrs(app_ctx):
    """forceSwitchTopic must not touch g.projectId, g.uuid, g.db, or g.baseTopic."""
    topics = [("t01", 1), ("t02", 1)]
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.baseTopic = "original_base"
    g.topic = "t01"

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te
    te.forceSwitchTopic()

    assert g.projectId == "test_proj"
    assert g.uuid == "test-user"
    assert g.baseTopic == "original_base"


# ---------------------------------------------------------------------------
# 6C-3: handle_tool_call dispatches correctly
# ---------------------------------------------------------------------------

def test_handle_tool_call_dispatches_force_switch(app_ctx):
    """handle_tool_call must call g.th.forceSwitchTopic when tool_calls present."""
    topics = [("t01", 1), ("t02", 1)]
    db = _DBStub()

    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te

    response = _ResponseStub("", [_ToolCallStub("interview_topic_over")])
    result = handle_tool_call(response)
    assert result == "t02", "handle_tool_call must trigger and return forceSwitchTopic result"


def test_handle_tool_call_returns_none_without_tool_calls(app_ctx):
    """handle_tool_call must return None when no tool_calls in response."""
    topics = [("t01", 1)]
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te

    response = _ResponseStub("just text", tool_calls=None)
    result = handle_tool_call(response)
    assert result is None


# ---------------------------------------------------------------------------
# 6C-4: force_switch_from_text delegates to forceSwitchTopic
# ---------------------------------------------------------------------------

def test_force_switch_from_text_calls_force_switch(app_ctx):
    """force_switch_from_text must call th.forceSwitchTopic()."""
    topics = [("t01", 1), ("t02", 1)]
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db
    g.topic = "t01"

    te = _make_engine(db, topics, current_topic="t01")
    g.th = te

    result = force_switch_from_text(te)
    assert result == "t02"


# ---------------------------------------------------------------------------
# 6C-5: strip_raw_tool_text handles various patterns
# ---------------------------------------------------------------------------

def test_strip_raw_tool_text_removes_function_call():
    """Must strip interview_topic_over({...}) artefacts."""
    text = 'interview_topic_over({"status":"done"}) What do you think?'
    assert strip_raw_tool_text(text) == "What do you think?"


def test_strip_raw_tool_text_handles_empty():
    """Must handle empty and None gracefully."""
    assert strip_raw_tool_text("") == ""
    assert strip_raw_tool_text(None) is None


def test_strip_raw_tool_text_preserves_clean_text():
    """Must leave clean text untouched."""
    text = "Tell me more about your experience."
    assert strip_raw_tool_text(text) == text


def test_strip_raw_tool_text_removes_only_tool_call():
    """When content is only the raw tool call, result should be empty string."""
    text = 'interview_topic_over({"status":"done"})'
    assert strip_raw_tool_text(text) == ""


# ---------------------------------------------------------------------------
# 6C-6: TOOL_SPEC schema validation
# ---------------------------------------------------------------------------

def test_tool_spec_schema_is_strict():
    """TOOL_SPEC must define a strict function with required 'status' param."""
    assert len(TOOL_SPEC) == 1
    fn = TOOL_SPEC[0]["function"]
    assert fn["name"] == "interview_topic_over"
    assert fn["strict"] is True
    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["additionalProperties"] is False
    assert params["required"] == ["status"]
    assert params["properties"]["status"]["enum"] == ["done"]


# ---------------------------------------------------------------------------
# 6C-7: getTopicProgress returns valid ratios
# ---------------------------------------------------------------------------

def test_progress_returns_correct_ratio(app_ctx):
    """getTopicProgress must compute current/total/ratio correctly."""
    topics = [("t01", 1), ("t02", 1), ("t03", 1)]
    # DB rows are 5-element: (id, topic_id, started_at, status, responses)
    db = _DBStub(
        topics_log=[(1, "t02", datetime.now(timezone.utc), 1, 0)],
    )
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db

    te = _make_engine(db, topics, current_topic="t02")
    progress = te.getTopicProgress()
    assert progress["total"] == 3
    assert progress["current"] == 2
    assert abs(progress["ratio"] - 2 / 3) < 0.01


def test_progress_handles_empty_topics(app_ctx):
    """getTopicProgress must return zeros when no topics exist."""
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db

    te = TopicEngine.__new__(TopicEngine)
    te.project = "test_proj"
    te.uuid = "test-user"
    te.DB = db
    te.topics = []
    te.topic = None

    progress = te.getTopicProgress()
    assert progress == {"current": 0, "total": 0, "ratio": 0}


# ---------------------------------------------------------------------------
# 6C-8: makeNewTopicLogEntry and changeLogEntryStatus write correct SQL
# ---------------------------------------------------------------------------

def test_make_new_topic_log_entry_inserts(app_ctx):
    """makeNewTopicLogEntry must INSERT with correct topic_id and user_id."""
    topics = [("t01", 1)]
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "test-user"
    g.db = db

    te = _make_engine(db, topics, current_topic="t01")
    te.makeNewTopicLogEntry("t01")

    assert len(db.inserts) == 1
    query, params = db.inserts[0]
    assert "INSERT" in query.upper()
    assert "topics_log" in query
    assert params[0] == "t01"
    assert params[1] == "test-user"


def test_change_log_entry_status_scoped_to_user(app_ctx):
    """changeLogEntryStatus must filter by both topic_id AND user_id."""
    topics = [("t01", 1), ("t02", 1)]
    db = _DBStub()
    g.projectId = "test_proj"
    g.uuid = "user-A"
    g.db = db

    te = _make_engine(db, topics, current_topic="t01")
    te.uuid = "user-A"
    te.changeLogEntryStatus()

    assert len(db.inserts) == 1
    query, params = db.inserts[0]
    assert "user_id" in query.lower(), "Must scope UPDATE to user_id"
    assert params == ("t01", "user-A")
