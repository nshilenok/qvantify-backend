from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import conversationInterface as ci


class _TopicStub:
    def __init__(self, topic_type="prompt"):
        self.topic_type = topic_type

    def findTopicById(self, topic_id):
        return (1, topic_id, "CURRENT TOPIC: What gives you the strongest rush?", 1)

    def findTopicLogEntry(self, topic_id):
        # status=1 means "open" for retrieveTopicStatus()
        return (1, 1, topic_id, datetime.now(timezone.utc), 1, 0)

    def getTopicType(self, topic_id):
        return self.topic_type


class _DBStub:
    def __init__(self, records):
        self.records = list(records)

    def query_database_all(self, query, params):
        if "FROM records" in query:
            return list(self.records)
        return []

    def store_message(self, role, message):
        topic = g.baseTopic if role == "user" else g.topic
        self.records.append((datetime.now(timezone.utc), role, message, topic))

    def query_database_one(self, query, params):
        if "SELECT defined_answers" in query:
            return (None,)
        return (None,)


class _ResponseMessage:
    def __init__(self, content):
        self.content = content
        self.tool_calls = None


class _ResponseChoice:
    def __init__(self, content):
        self.message = _ResponseMessage(content)


class _ResponseStub:
    def __init__(self, content):
        self.choices = [_ResponseChoice(content)]


class _LLMStub:
    last_messages = None
    last_tools = None

    def __init__(self, *args, **kwargs):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMStub.last_messages = messages
        _LLMStub.last_tools = tools
        return _ResponseStub("assistant result")


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


def _seed_context(db_stub):
    g.projectId = "swipking2"
    g.uuid = "test-user"
    g.topic = "swipking2_t03"
    g.baseTopic = "swipking2_t03"
    g.db = db_stub


def test_build_model_messages_uses_single_current_system_prompt(app_ctx):
    records = [
        (datetime.now(timezone.utc), "system", "OLD SYSTEM SHOULD NOT REPLAY", "swipking2_t01"),
        (datetime.now(timezone.utc), "assistant", "What gives you the strongest rush?", "swipking2_t03"),
        (datetime.now(timezone.utc), "user", "ability to get money quickly", "swipking2_t03"),
        (datetime.now(timezone.utc), "system", "CURRENT SYSTEM FROM DB SHOULD NOT REPLAY", "swipking2_t03"),
    ]
    db = _DBStub(records)
    _seed_context(db)
    chat = ci.conversation(_TopicStub())
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT: one question only"

    messages = chat.buildModelMessages()

    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == (
        "CURRENT TOPIC: What gives you the strongest rush?\n \nDEFAULT PROMPT: one question only"
    )
    assert sum(1 for m in messages if m["role"] == "system") == 1
    assert [m["role"] for m in messages[1:]] == ["assistant", "user"]
    joined = "\n".join(m["content"] for m in messages)
    assert "OLD SYSTEM SHOULD NOT REPLAY" not in joined
    assert "CURRENT SYSTEM FROM DB SHOULD NOT REPLAY" not in joined


def test_provide_response_sends_single_system_plus_history(app_ctx, monkeypatch):
    records = [
        (datetime.now(timezone.utc), "assistant", "What gives you the strongest rush?", "swipking2_t03"),
        (datetime.now(timezone.utc), "user", "ability to get money quickly", "swipking2_t03"),
        (datetime.now(timezone.utc), "system", "LEGACY SYSTEM CONTENT", "swipking2_t02"),
    ]
    db = _DBStub(records)
    _seed_context(db)
    g.topicIsChanging = None
    _LLMStub.last_messages = None
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub(topic_type="prompt"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT: one question only"

    out = chat.provideResponse("I need cash fast")
    assert out == "assistant result"

    sent = _LLMStub.last_messages
    assert sent is not None
    assert sum(1 for m in sent if m["role"] == "system") == 1
    assert sent[0]["role"] == "system"
    assert sent[1]["role"] == "assistant"
    assert sent[2]["role"] == "user"
    assert sent[3]["role"] == "user"
    assert sent[3]["content"] == "I need cash fast"
    assert "LEGACY SYSTEM CONTENT" not in "\n".join(m["content"] for m in sent)


def test_provide_response_topic_change_still_sends_one_system(app_ctx, monkeypatch):
    records = [
        (datetime.now(timezone.utc), "assistant", "When do you play and why?", "swipking2_t02"),
        (datetime.now(timezone.utc), "user", "just for fun", "swipking2_t02"),
    ]
    db = _DBStub(records)
    _seed_context(db)
    g.topicIsChanging = True
    _LLMStub.last_messages = None
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub(topic_type="prompt"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT: one question only"

    out = chat.provideResponse("money rush")
    assert out == "assistant result"
    sent = _LLMStub.last_messages
    assert sent is not None
    assert sum(1 for m in sent if m["role"] == "system") == 1


def test_streaming_path_reuses_canonical_builder():
    server_path = Path(__file__).resolve().parents[1] / "server.py"
    source = server_path.read_text(encoding="utf-8")
    assert "messages = chat.buildModelMessages()" in source
    assert "llm.streamResponseOpenAI(messages, tools=tools)" in source

