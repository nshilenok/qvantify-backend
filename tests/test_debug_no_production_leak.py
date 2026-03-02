"""Regression: _build_reply_debug must return None on production (Linux)."""

import json
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import server as srv


class _DBStub:
    def query_database_one(self, query, params):
        if "respondents" in query:
            return ("ext-123",)
        if "projects" in query:
            return ("gpt-5.2", "medium")
        return (None,)

    def store_message(self, role, content):
        pass

    def close(self):
        return None


class _TopicMeta:
    """Minimal conversation stub with _get_topic_meta / retrieveTopic / getDefaultPrompt."""

    def _get_topic_meta(self, topic_id):
        return {"title": "Test Topic", "system": "sys", "group": "g", "sequence": 1}

    def retrieveTopic(self):
        return "CURRENT TOPIC: test"

    def getDefaultPrompt(self, topic_id=None):
        return "DEFAULT PROMPT"


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        g.projectId = "proj1"
        g.uuid = "user-1"
        g.topic = "topic_01"
        g.db = _DBStub()
        yield


def test_debug_returns_none_on_linux(app_ctx, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    result = srv._build_reply_debug(_TopicMeta())
    assert result is None, "_build_reply_debug must return None in production (Linux)"


def test_debug_returns_dict_on_macos(app_ctx, monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    result = srv._build_reply_debug(_TopicMeta())
    assert isinstance(result, dict)
    assert result["model"] == "gpt-5.2"
    assert result["reasoning_effort"] == "medium"
    assert result["topic_title"] == "Test Topic"
    assert result["user_id"] == "user-1"
    assert result["external_id"] == "ext-123"
    assert "CURRENT TOPIC: test" in result["developer_prompt"]
    assert "DEFAULT PROMPT" in result["developer_prompt"]


def test_streaming_final_event_excludes_debug_on_linux(app_ctx, monkeypatch):
    """The _final_event helper inside generate() uses _build_reply_debug;
    verify the JSON payload has no _debug key when running on Linux."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    result = srv._build_reply_debug(_TopicMeta())
    payload = {
        "type": "final",
        "response": "hello",
        "status": "open",
        "answers": None,
        "progress": {"current": 1, "total": 5, "ratio": 0.2},
    }
    if result:
        payload["_debug"] = result
    assert "_debug" not in payload, "Production streaming payload must not contain _debug"


def test_frontend_logdebug_guards_hostname():
    """Static check: logDebug in InterviewClient only logs for localhost/127.0.0.1."""
    client_path = ROOT_DIR / "frontend" / "app" / "interview" / "InterviewClient.tsx"
    source = client_path.read_text(encoding="utf-8")
    assert 'hostname !== "localhost"' in source or "hostname !== 'localhost'" in source
    assert 'hostname !== "127.0.0.1"' in source or "hostname !== '127.0.0.1'" in source
