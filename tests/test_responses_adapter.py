"""Tests for the OpenAI Responses API adapter and transport routing.

Covers:
- _ResponsesCompat adapter normalization (text, tool calls, usage)
- Transport selector: getOpenAITransport reads DB flag
- LLM routing: allow_responses + transport=responses → Responses path
- LLM routing: allow_responses=False → always Chat Completions
- Tool spec translation from Chat format to Responses format
- tool_choice translation
- Message conversion (system → instructions, history → input)
"""

from pathlib import Path
import sys
import json

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llmInterface as li


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _DBStubResponses:
    """DB stub that returns openai_transport='responses'."""
    def __init__(self, api="openai", transport="responses"):
        self.api = api
        self._transport = transport

    def query_database_one(self, query, params):
        q = query.lower()
        if q.startswith("select api from projects"):
            return (self.api,)
        if "openai_transport" in q:
            return (self._transport,)
        if "max_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.4", 0.7, 120, 1, self.api, "low")
        if "max_completion_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.4", 0.7, 120, 1, self.api, "low")
        raise Exception(f"Unexpected query: {query}")

    def query_database_insert(self, query, params):
        return None


class _DBStubChatCompletions:
    """DB stub that returns openai_transport='chat_completions'."""
    def __init__(self, api="openai"):
        self.api = api

    def query_database_one(self, query, params):
        q = query.lower()
        if q.startswith("select api from projects"):
            return (self.api,)
        if "openai_transport" in q:
            return ("chat_completions",)
        if "max_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.4", 0.7, 120, 1, self.api, "low")
        if "max_completion_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.4", 0.7, 120, 1, self.api, "low")
        raise Exception(f"Unexpected query: {query}")

    def query_database_insert(self, query, params):
        return None


class _DBStubNoTransportColumn:
    """DB stub where openai_transport column does not exist."""
    def __init__(self, api="openai"):
        self.api = api

    def query_database_one(self, query, params):
        q = query.lower()
        if q.startswith("select api from projects"):
            return (self.api,)
        if "openai_transport" in q:
            raise Exception("column openai_transport does not exist")
        if "max_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.2", 0.7, 120, 1, self.api, "low")
        if "max_completion_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.2", 0.7, 120, 1, self.api, "low")
        raise Exception(f"Unexpected query: {query}")

    def query_database_insert(self, query, params):
        return None


class _FakeResponsesAPI:
    """Captures client.responses.create() calls."""
    captured_kwargs = []

    class _ContentPart:
        def __init__(self):
            self.type = "output_text"
            self.text = "Hello from Responses"

    class _OutputMessage:
        def __init__(self):
            self.type = "message"
            self.content = [_FakeResponsesAPI._ContentPart()]

    class _Usage:
        def __init__(self):
            self.input_tokens = 42
            self.output_tokens = 17
            self.total_tokens = 59

    class _Result:
        def __init__(self):
            self.output = [_FakeResponsesAPI._OutputMessage()]
            self.usage = _FakeResponsesAPI._Usage()

    def create(self, **kwargs):
        _FakeResponsesAPI.captured_kwargs.append(kwargs)
        return self._Result()


class _FakeResponsesAPIWithToolCall:
    """Returns a function_call output item."""
    captured_kwargs = []

    class _FunctionCall:
        def __init__(self):
            self.type = "function_call"
            self.name = "interview_topic_over"
            self.arguments = '{"status":"done"}'
            self.call_id = "call_abc123"

    class _Usage:
        def __init__(self):
            self.input_tokens = 50
            self.output_tokens = 10
            self.total_tokens = 60

    class _Result:
        def __init__(self):
            self.output = [_FakeResponsesAPIWithToolCall._FunctionCall()]
            self.usage = _FakeResponsesAPIWithToolCall._Usage()

    def create(self, **kwargs):
        _FakeResponsesAPIWithToolCall.captured_kwargs.append(kwargs)
        return self._Result()


class _FakeOpenAIClientForResponses:
    """Fake OpenAI client that routes .responses to a fake."""
    def __init__(self, responses_api):
        self.responses = responses_api

    def close(self):
        pass


class _FakeChatCompletionsAPI:
    """Captures client.chat.completions.create() calls."""
    captured_kwargs = []

    class _ResponseStub:
        pass

    def create(self, **kwargs):
        _FakeChatCompletionsAPI.captured_kwargs.append(kwargs)
        return self._ResponseStub()


class _FakeOpenAIClientForChat:
    """Fake OpenAI client that routes .chat.completions to a fake."""
    def __init__(self, chat_api):
        class _Chat:
            completions = chat_api
        self.chat = _Chat()

    def close(self):
        pass


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        g.projectId = "test_project"
        yield


# ---------------------------------------------------------------------------
# _ResponsesCompat adapter tests
# ---------------------------------------------------------------------------

class TestResponsesCompat:

    def test_text_output_normalized(self):
        class _Part:
            type = "output_text"
            text = "Hello world"

        class _Msg:
            type = "message"
            content = [_Part()]

        class _Usage:
            input_tokens = 10
            output_tokens = 5
            total_tokens = 15

        class _Result:
            output = [_Msg()]
            usage = _Usage()

        compat = li._ResponsesCompat(_Result())
        assert compat.choices[0].message.content == "Hello world"
        assert compat.choices[0].message.tool_calls is None
        assert compat.usage.prompt_tokens == 10
        assert compat.usage.completion_tokens == 5

    def test_function_call_normalized(self):
        class _FnCall:
            type = "function_call"
            name = "interview_topic_over"
            arguments = '{"status":"done"}'
            call_id = "call_123"

        class _Usage:
            input_tokens = 20
            output_tokens = 8
            total_tokens = 28

        class _Result:
            output = [_FnCall()]
            usage = _Usage()

        compat = li._ResponsesCompat(_Result())
        assert compat.choices[0].message.content is None
        tc = compat.choices[0].message.tool_calls
        assert tc is not None
        assert len(tc) == 1
        assert tc[0].function.name == "interview_topic_over"
        assert json.loads(tc[0].function.arguments) == {"status": "done"}

    def test_mixed_text_and_tool_call(self):
        class _Part:
            type = "output_text"
            text = "Follow-up question here"

        class _Msg:
            type = "message"
            content = [_Part()]

        class _FnCall:
            type = "function_call"
            name = "interview_topic_over"
            arguments = '{"status":"done"}'
            call_id = "call_456"

        class _Usage:
            input_tokens = 30
            output_tokens = 12
            total_tokens = 42

        class _Result:
            output = [_Msg(), _FnCall()]
            usage = _Usage()

        compat = li._ResponsesCompat(_Result())
        assert compat.choices[0].message.content == "Follow-up question here"
        assert len(compat.choices[0].message.tool_calls) == 1

    def test_empty_output(self):
        class _Usage:
            input_tokens = 5
            output_tokens = 0
            total_tokens = 5

        class _Result:
            output = []
            usage = _Usage()

        compat = li._ResponsesCompat(_Result())
        assert compat.choices[0].message.content is None
        assert compat.choices[0].message.tool_calls is None

    def test_no_usage(self):
        class _Result:
            output = []
            usage = None

        compat = li._ResponsesCompat(_Result())
        assert compat.usage.prompt_tokens == 0
        assert compat.usage.completion_tokens == 0


# ---------------------------------------------------------------------------
# Transport selector tests
# ---------------------------------------------------------------------------

class TestTransportSelector:

    def test_allow_responses_reads_db_flag(self, app_ctx):
        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=True)
        assert llm._openai_transport == "responses"

    def test_allow_responses_false_ignores_db_flag(self, app_ctx):
        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=False)
        assert llm._openai_transport == "chat_completions"

    def test_default_constructor_uses_chat_completions(self, app_ctx):
        llm = li.LLM(db=_DBStubChatCompletions(), project_id="proj")
        assert llm._openai_transport == "chat_completions"

    def test_missing_column_falls_back_to_chat_completions(self, app_ctx):
        llm = li.LLM(db=_DBStubNoTransportColumn(), project_id="proj", allow_responses=True)
        assert llm._openai_transport == "chat_completions"

    def test_chat_completions_flag_value(self, app_ctx):
        llm = li.LLM(db=_DBStubChatCompletions(), project_id="proj", allow_responses=True)
        assert llm._openai_transport == "chat_completions"


# ---------------------------------------------------------------------------
# Tool spec translation tests
# ---------------------------------------------------------------------------

class TestToolTranslation:

    def test_translate_interview_tool_spec(self):
        chat_tools = [
            {
                "type": "function",
                "function": {
                    "name": "interview_topic_over",
                    "description": "Call only when CURRENT TOPIC is complete.",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["done"],
                            }
                        },
                        "required": ["status"],
                    },
                },
            }
        ]
        result = li.LLM._translate_tools_for_responses(chat_tools)
        assert result is not None
        assert len(result) == 1
        tool = result[0]
        assert tool["type"] == "function"
        assert tool["name"] == "interview_topic_over"
        assert tool["strict"] is True
        assert tool["parameters"]["properties"]["status"]["enum"] == ["done"]

    def test_translate_analysis_tool_spec(self):
        chat_tools = [
            {
                "type": "function",
                "function": {
                    "name": "session_analysis",
                    "description": "Return analysis results.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "persona_label": {"type": "string"},
                            "findings_summary": {"type": "string"},
                        },
                        "required": ["persona_label", "findings_summary"],
                    },
                },
            }
        ]
        result = li.LLM._translate_tools_for_responses(chat_tools)
        assert len(result) == 1
        assert result[0]["name"] == "session_analysis"
        assert result[0]["strict"] is False

    def test_translate_none_tools(self):
        assert li.LLM._translate_tools_for_responses(None) is None

    def test_translate_empty_tools(self):
        assert li.LLM._translate_tools_for_responses([]) is None

    def test_translate_tool_choice_auto(self):
        assert li.LLM._translate_tool_choice_for_responses(None) == "auto"

    def test_translate_tool_choice_forced_function(self):
        tc = {"type": "function", "function": {"name": "session_analysis"}}
        result = li.LLM._translate_tool_choice_for_responses(tc)
        assert result == {"type": "function", "name": "session_analysis"}


# ---------------------------------------------------------------------------
# Routing tests: Responses vs Chat Completions dispatch
# ---------------------------------------------------------------------------

class TestRouting:

    def test_responses_path_used_when_flagged(self, app_ctx, monkeypatch):
        _FakeResponsesAPI.captured_kwargs = []
        fake_responses = _FakeResponsesAPI()
        fake_client = _FakeOpenAIClientForResponses(fake_responses)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=True)
        result = llm.getResponse([{"role": "system", "content": "test"}])

        assert _FakeResponsesAPI.captured_kwargs, "Responses API was not called"
        payload = _FakeResponsesAPI.captured_kwargs[-1]
        assert payload["model"] == "gpt-5.4"
        assert payload["instructions"] == "test"
        assert result.choices[0].message.content == "Hello from Responses"

    def test_chat_path_when_not_flagged(self, app_ctx, monkeypatch):
        _FakeChatCompletionsAPI.captured_kwargs = []
        fake_chat = _FakeChatCompletionsAPI()
        fake_client = _FakeOpenAIClientForChat(fake_chat)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        llm = li.LLM(db=_DBStubChatCompletions(), project_id="proj", allow_responses=True)
        llm.getResponse([{"role": "user", "content": "ping"}])

        assert _FakeChatCompletionsAPI.captured_kwargs, "Chat API was not called"

    def test_chat_path_when_allow_responses_false(self, app_ctx, monkeypatch):
        _FakeChatCompletionsAPI.captured_kwargs = []
        fake_chat = _FakeChatCompletionsAPI()
        fake_client = _FakeOpenAIClientForChat(fake_chat)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=False)
        llm.getResponse([{"role": "user", "content": "ping"}])

        assert _FakeChatCompletionsAPI.captured_kwargs, "Chat API was not called"

    def test_responses_path_with_tools(self, app_ctx, monkeypatch):
        _FakeResponsesAPIWithToolCall.captured_kwargs = []
        fake_responses = _FakeResponsesAPIWithToolCall()
        fake_client = _FakeOpenAIClientForResponses(fake_responses)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "interview_topic_over",
                    "description": "done",
                    "strict": True,
                    "parameters": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"status": {"type": "string", "enum": ["done"]}},
                        "required": ["status"],
                    },
                },
            }
        ]

        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=True)
        result = llm.getResponse(
            [{"role": "system", "content": "interview prompt"}, {"role": "user", "content": "test"}],
            tools=tools,
        )

        payload = _FakeResponsesAPIWithToolCall.captured_kwargs[-1]
        assert payload["instructions"] == "interview prompt"
        assert payload["input"] == [{"role": "user", "content": "test"}]
        assert len(payload["tools"]) == 1
        assert payload["tools"][0]["name"] == "interview_topic_over"
        assert payload["reasoning"] == {"effort": "low"}

        tc = result.choices[0].message.tool_calls
        assert tc is not None
        assert tc[0].function.name == "interview_topic_over"

    def test_responses_max_output_tokens_floor(self, app_ctx, monkeypatch):
        _FakeResponsesAPI.captured_kwargs = []
        fake_responses = _FakeResponsesAPI()
        fake_client = _FakeOpenAIClientForResponses(fake_responses)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=True)
        llm.config["max_tokens"] = 5
        llm.getResponse([{"role": "user", "content": "hi"}])

        payload = _FakeResponsesAPI.captured_kwargs[-1]
        assert payload["max_output_tokens"] >= 16

    def test_non_openai_api_ignores_responses(self, app_ctx, monkeypatch):
        """OpenRouter projects should never use the Responses path."""
        llm = li.LLM(db=_DBStubResponses(api="openrouter", transport="responses"),
                      project_id="proj", allow_responses=True)
        assert llm.api == "openrouter"
        assert llm._openai_transport == "responses"

    def test_responses_sends_begin_when_only_system_message(self, app_ctx, monkeypatch):
        """When only a system message is provided, Responses must receive a
        synthetic 'Begin.' user input so the API doesn't reject the request."""
        _FakeResponsesAPI.captured_kwargs = []
        fake_responses = _FakeResponsesAPI()
        fake_client = _FakeOpenAIClientForResponses(fake_responses)
        monkeypatch.setattr(li, "OpenAI", lambda **kw: fake_client)
        monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

        llm = li.LLM(db=_DBStubResponses(), project_id="proj", allow_responses=True)
        llm.getResponse([{"role": "system", "content": "You are interviewing."}])

        payload = _FakeResponsesAPI.captured_kwargs[-1]
        assert payload["instructions"] == "You are interviewing."
        assert payload["input"] == [{"role": "user", "content": "Begin."}]
