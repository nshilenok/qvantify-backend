import json
from pathlib import Path
import sys

import pytest
from flask import g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server as srv


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


class _DBStub:
    def __init__(self):
        self.messages = []

    def store_message(self, role, content):
        self.messages.append((role, content))

    def close(self):
        return None


class _TopicHandlerAutoStub:
    def getTopicType(self, _topic):
        return "auto"

    def getTopicProgress(self):
        return {"current": 2, "total": 11, "ratio": 2 / 11}


class _TopicHandlerPromptStub:
    def getTopicType(self, _topic):
        return "prompt"

    def getTopicProgress(self):
        return {"current": 1, "total": 11, "ratio": 1 / 11}


class _ConversationAutoStub:
    def __init__(self, _th):
        self.DB = g.db

    def buildModelMessages(self):
        return [{"role": "system", "content": "CURRENT TOPIC: purchase blockers"}]

    def retrieveTopicStatus(self):
        return "open"

    def retrieveDefinedAnswers(self):
        return None

    def provideInitialResponse(self):
        return "next topic question"


class _ConversationPromptStub:
    def __init__(self, _th):
        self.DB = g.db

    def buildModelMessages(self):
        return [{"role": "system", "content": "CURRENT TOPIC: prompt topic"}]

    def retrieveTopicStatus(self):
        return "open"

    def retrieveDefinedAnswers(self):
        return None


class _ToolFunctionStub:
    def __init__(self, name):
        self.name = name


class _ToolCallStub:
    def __init__(self, name):
        self.function = _ToolFunctionStub(name)


class _ResponseMessageStub:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


class _ResponseChoiceStub:
    def __init__(self, message):
        self.message = message


class _ResponseStub:
    def __init__(self, content, tool_calls):
        self.choices = [_ResponseChoiceStub(_ResponseMessageStub(content, tool_calls))]


class _LLMAutoStub:
    last_messages = None
    last_tools = None

    def __init__(self, *args, **kwargs):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMAutoStub.last_messages = messages
        _LLMAutoStub.last_tools = tools
        # Simulate an auto topic transition tool call with no text deltas.
        return _ResponseStub("", [_ToolCallStub("interview_topic_over")])

    def streamResponseOpenAI(self, messages, tools=None):
        raise AssertionError("Auto streaming path should not use streamResponseOpenAI")


class _LLMPromptStub:
    last_tools = None

    def __init__(self, *args, **kwargs):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        raise AssertionError("Prompt streaming path should not use getResponse")

    def streamResponseOpenAI(self, messages, tools=None):
        _LLMPromptStub.last_tools = tools
        yield ("delta", "Hello")
        yield ("delta", " world")
        yield ("done", None)


def test_reply_stream_auto_path_emits_keepalive_uses_tools_and_returns_final(monkeypatch):
    monkeypatch.setattr(srv, "check_if_user_exists", lambda: None)
    monkeypatch.setattr(srv, "conversation", _ConversationAutoStub)
    monkeypatch.setattr(srv, "LLM", _LLMAutoStub)
    monkeypatch.setattr(srv.autoTopic, "switchTopic", lambda response: "swipking3_t02")
    monkeypatch.setattr(srv, "_analysis_needed", lambda project_id, respondent_id: False)

    db = _DBStub()
    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "swipking3", "uuid": "test-user", "Accept": "text/event-stream"},
        json={"message": "no", "stream": True},
    ):
        g.projectId = "swipking3"
        g.uuid = "test-user"
        g.topic = "swipking3_t01"
        g.topicIsChanging = None
        g.th = _TopicHandlerAutoStub()
        g.db = db

        response = srv.gpt_response()
        assert response.status_code == 200

        body = _drain_response_text(response)
        assert body.startswith(":\n\n"), "SSE keepalive must be emitted immediately"

        payloads = _extract_sse_payloads(body)
        final = next((p for p in payloads if p.get("type") == "final"), None)
        assert final is not None, "Auto streaming path must always end with a final event"
        assert final["response"] == "next topic question"
        assert final["status"] == "open"

        assert _LLMAutoStub.last_tools is not None, "Auto topic must pass tools into LLM call"
        assert _LLMAutoStub.last_tools[0]["function"]["name"] == "interview_topic_over"
        # No empty assistant message should leak into records on tool-call switch.
        assert ("assistant", "") not in db.messages


def test_reply_stream_prompt_path_still_streams_delta_and_final(monkeypatch):
    monkeypatch.setattr(srv, "check_if_user_exists", lambda: None)
    monkeypatch.setattr(srv, "conversation", _ConversationPromptStub)
    monkeypatch.setattr(srv, "LLM", _LLMPromptStub)
    monkeypatch.setattr(srv, "_analysis_needed", lambda project_id, respondent_id: False)

    db = _DBStub()
    with srv.app.test_request_context(
        "/api/reply/",
        method="POST",
        headers={"projectId": "swipking2", "uuid": "test-user", "Accept": "text/event-stream"},
        json={"message": "ok", "stream": True},
    ):
        g.projectId = "swipking2"
        g.uuid = "test-user"
        g.topic = "swipking2_t01"
        g.topicIsChanging = None
        g.th = _TopicHandlerPromptStub()
        g.db = db

        response = srv.gpt_response()
        assert response.status_code == 200

        body = _drain_response_text(response)
        assert body.startswith(":\n\n"), "Prompt streaming path must also flush headers immediately"

        payloads = _extract_sse_payloads(body)
        deltas = [p for p in payloads if p.get("type") == "delta"]
        final = next((p for p in payloads if p.get("type") == "final"), None)

        assert len(deltas) >= 2
        assert final is not None
        assert final["response"] == "Hello world"
        assert final["status"] == "open"
        assert _LLMPromptStub.last_tools is None
        assert ("assistant", "Hello world") in db.messages

