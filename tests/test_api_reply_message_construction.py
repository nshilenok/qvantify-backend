from datetime import datetime, timezone
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import interview.conversation as ci


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

    def store_message(self, project_id, user_id, base_topic, current_topic,
                      role, message, voice_input=False, audio_tokens=0):
        topic = base_topic if role == "user" else current_topic
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
    handler_path = Path(__file__).resolve().parents[1] / "interview" / "reply_handler.py"
    source = handler_path.read_text(encoding="utf-8")
    assert "self.chat.buildModelMessages(" in source
    assert "llm.streamResponse(messages, tools=tools)" in source


def test_provide_initial_response_on_topic_switch_includes_prior_history(app_ctx, monkeypatch):
    """
    Regression: when a topic switch occurs, provideInitialResponse must send the full
    prior conversation history to the LLM, not just the new system prompt.
    Without the fix the user's "no" answer on topic 1 would be invisible to topic 2.
    """
    records = [
        # Topic 1 exchange: assistant asked, user answered "no"
        (datetime.now(timezone.utc), "assistant", "Have you ever tried to make a purchase?", "swipking3_t01"),
        (datetime.now(timezone.utc), "user", "no", "swipking3_t01"),
    ]
    db = _DBStub(records)

    # Simulate being on the new topic (t02) after a switch
    g.projectId = "swipking3"
    g.uuid = "test-user"
    g.topic = "swipking3_t02"
    g.baseTopic = "swipking3_t02"
    g.topicIsChanging = True
    g.db = db

    _LLMStub.last_messages = None
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    topic_stub = _TopicStub(topic_type="auto")
    # Override findTopicById for new topic
    topic_stub.findTopicById = lambda tid: (2, tid, "CURRENT TOPIC: Why haven't you bought yet?", 2)

    chat = ci.conversation(topic_stub)
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT: one question only"

    out = chat.provideInitialResponse()
    assert out == "assistant result"

    sent = _LLMStub.last_messages
    assert sent is not None, "LLM was not called"

    # System prompt must be present and be the new topic's prompt
    assert sent[0]["role"] == "system"
    assert "CURRENT TOPIC: Why haven't you bought yet?" in sent[0]["content"]

    # Prior user/assistant turns must be present
    roles_after_system = [m["role"] for m in sent[1:]]
    assert "user" in roles_after_system, "Prior user turn missing from LLM context on topic switch"
    assert "assistant" in roles_after_system, "Prior assistant turn missing from LLM context on topic switch"

    # The actual "no" answer must be in context
    all_content = "\n".join(m["content"] for m in sent)
    assert "no" in all_content, "User's prior answer not present in LLM context on topic switch"

    # Tools must NOT be passed for initial responses (opening question should never offer topic-done tool)
    assert _LLMStub.last_tools is None, "provideInitialResponse must not pass tools — the opening question has nothing to mark done"


def test_provide_initial_response_auto_no_tools(app_ctx, monkeypatch):
    """provideInitialResponse must NOT pass tools, even for auto topics.
    The opening question for a new topic should never offer interview_topic_over."""
    db = _DBStub([])
    g.projectId = "swipking3"
    g.uuid = "test-user"
    g.topic = "swipking3_t01"
    g.baseTopic = "swipking3_t01"
    g.topicIsChanging = True
    g.db = db

    _LLMStub.last_tools = "SENTINEL"
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub(topic_type="auto"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"

    chat.provideInitialResponse()

    assert _LLMStub.last_tools is None, "Tools should NOT be passed for initial responses"


def test_provide_initial_response_prompt_no_tools(app_ctx, monkeypatch):
    """provideInitialResponse must NOT pass tools for prompt topics."""
    db = _DBStub([])
    g.projectId = "swipking2"
    g.uuid = "test-user"
    g.topic = "swipking2_t01"
    g.baseTopic = "swipking2_t01"
    g.topicIsChanging = True
    g.db = db

    _LLMStub.last_tools = "SENTINEL"
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    chat = ci.conversation(_TopicStub(topic_type="prompt"))
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"

    chat.provideInitialResponse()

    assert _LLMStub.last_tools is None, "Tools should NOT be passed for prompt topics"


def test_messages_are_strictly_chronological_after_topic_switch(app_ctx, monkeypatch):
    """After a topic switch, the messages sent to the LLM must be in strict
    chronological order: [developer, assistant, user, assistant, user, ...].
    No consecutive same-role messages allowed."""
    now = datetime.now(timezone.utc)
    records = [
        (now, "system", "OLD SYSTEM", "swipking3_t00"),
        (now, "assistant", "Welcome! Ready?", "swipking3_t00"),
        (now, "user", "yes", "swipking3_t00"),
        (now, "assistant", "Have you ever tried to make a purchase?", "swipking3_t01"),
        (now, "user", "no", "swipking3_t01"),
    ]
    db = _DBStub(records)
    g.projectId = "swipking3"
    g.uuid = "test-user"
    g.topic = "swipking3_t02"
    g.baseTopic = "swipking3_t02"
    g.topicIsChanging = True
    g.db = db

    _LLMStub.last_messages = None
    monkeypatch.setattr(ci, "LLM", _LLMStub)

    topic_stub = _TopicStub(topic_type="prompt")
    topic_stub.findTopicById = lambda tid: (3, tid, "CURRENT TOPIC: Scenario B question", 3)
    chat = ci.conversation(topic_stub)
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT PROMPT"

    chat.provideInitialResponse()
    sent = _LLMStub.last_messages
    assert sent is not None

    # First message must be system/developer
    assert sent[0]["role"] == "system"

    # Remaining messages must alternate assistant/user and be in chronological order
    roles = [m["role"] for m in sent[1:]]
    for i in range(1, len(roles)):
        assert roles[i] != roles[i - 1], (
            f"Consecutive same-role messages at positions {i-1},{i}: "
            f"{roles[i-1]}, {roles[i]} — full roles: {roles}"
        )

    # The user's "no" must be present
    contents = [m["content"] for m in sent]
    assert "no" in contents, "User's 'no' answer must be in LLM context"

    # The old system prompt must NOT be in the messages
    joined = "\n".join(contents)
    assert "OLD SYSTEM" not in joined


def test_tool_history_never_leaks_into_messages(app_ctx, monkeypatch):
    """Records with role 'tool' or 'function' must never appear in buildModelMessages.
    Even if such rows existed in the DB, they must be filtered out."""
    now = datetime.now(timezone.utc)
    records = [
        (now, "assistant", "Have you ever tried?", "t01"),
        (now, "user", "no", "t01"),
        (now, "tool", '{"status":"done"}', "t01"),
        (now, "function", '{"result":"ok"}', "t01"),
        (now, "system", "SYSTEM MSG", "t01"),
    ]
    db = _DBStub(records)
    g.projectId = "swipking3"
    g.uuid = "test-user"
    g.topic = "t02"
    g.baseTopic = "t02"
    g.db = db

    chat = ci.conversation(_TopicStub())
    chat.getDefaultPrompt = lambda topic_id=None: "DEFAULT"

    messages = chat.buildModelMessages()
    roles = [m["role"] for m in messages]
    assert "tool" not in roles, "tool role must never be in messages"
    assert "function" not in roles, "function role must never be in messages"
    assert roles.count("system") == 1, "Only one system message (the fresh prompt)"
    assert roles == ["system", "assistant", "user"]

