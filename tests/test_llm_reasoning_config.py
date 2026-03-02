from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import llmInterface as li


class _ResponseStub:
    pass


class _LegacyNoReasoningDB:
    def query_database_one(self, query, params):
        q = query.lower()
        if q.startswith("select api from projects"):
            return ("openai",)
        if "max_completion_tokens,top_p,api from projects" in q and "reasoning_effort" not in q:
            return ("gpt-5.2", 0.7, 120, 1, "openai")
        raise Exception("Column does not exist")

    def query_database_insert(self, query, params):
        return None


class _ReasoningDB:
    def __init__(self, api="openai"):
        self.api = api

    def query_database_one(self, query, params):
        q = query.lower()
        if q.startswith("select api from projects"):
            return (self.api,)
        if "max_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.2", 0.7, 120, 1, self.api, "low")
        if "max_completion_tokens,top_p,api,reasoning_effort" in q:
            return ("gpt-5.2", 0.7, 120, 1, self.api, "low")
        raise Exception(f"Unexpected query: {query}")

    def query_database_insert(self, query, params):
        return None


class _FakeOpenAI:
    captured_kwargs = []

    def __init__(self, *args, **kwargs):
        class _Completions:
            def create(self, **kwargs):
                _FakeOpenAI.captured_kwargs.append(kwargs)
                return _ResponseStub()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()

    def close(self):
        return None


class _FakeAzureOpenAI:
    captured_kwargs = []

    def __init__(self, *args, **kwargs):
        class _Completions:
            def create(self, **kwargs):
                _FakeAzureOpenAI.captured_kwargs.append(kwargs)
                return _ResponseStub()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()

    def close(self):
        return None


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        g.projectId = "sample_project"
        yield


def test_config_falls_back_to_low_reasoning_without_reasoning_column(app_ctx):
    llm = li.LLM(db=_LegacyNoReasoningDB())
    assert llm.config["model"] == "gpt-5.2"
    assert llm.config["reasoning_effort"] == "low"


def test_openai_gpt5_requests_include_low_reasoning_and_max_completion_tokens(app_ctx, monkeypatch):
    _FakeOpenAI.captured_kwargs = []
    monkeypatch.setattr(li, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

    llm = li.LLM(db=_ReasoningDB(api="openai"))
    llm.getResponseOpenAI([{"role": "user", "content": "ping"}])

    assert _FakeOpenAI.captured_kwargs, "OpenAI client was not called"
    payload = _FakeOpenAI.captured_kwargs[-1]
    assert payload["model"] == "gpt-5.2"
    assert payload["reasoning_effort"] == "low"
    assert "max_completion_tokens" in payload
    assert "max_tokens" not in payload


def test_openai_gpt5_promotes_leading_system_message_to_developer(app_ctx, monkeypatch):
    _FakeOpenAI.captured_kwargs = []
    monkeypatch.setattr(li, "OpenAI", _FakeOpenAI)
    monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)

    llm = li.LLM(db=_ReasoningDB(api="openai"))
    original_messages = [
        {"role": "system", "content": "follow topic strictly"},
        {"role": "user", "content": "ping"},
    ]
    llm.getResponseOpenAI(original_messages)

    assert _FakeOpenAI.captured_kwargs, "OpenAI client was not called"
    payload = _FakeOpenAI.captured_kwargs[-1]
    assert payload["messages"][0]["role"] == "developer"
    assert payload["messages"][0]["content"] == "follow topic strictly"
    assert payload["messages"][1]["role"] == "user"
    assert original_messages[0]["role"] == "system"


def test_azure_requests_strip_reasoning_effort(app_ctx, monkeypatch):
    _FakeAzureOpenAI.captured_kwargs = []
    monkeypatch.setattr(li, "AzureOpenAI", _FakeAzureOpenAI)
    monkeypatch.setattr(li.LLM, "saveUsage", lambda self, response: None)
    monkeypatch.setattr(li.credentials, "azureopenai_key", "test-azure-key")

    llm = li.LLM(db=_ReasoningDB(api="azure"))
    llm.getResponseAzure([{"role": "user", "content": "ping"}])

    assert _FakeAzureOpenAI.captured_kwargs, "Azure client was not called"
    payload = _FakeAzureOpenAI.captured_kwargs[-1]
    assert "reasoning_effort" not in payload

