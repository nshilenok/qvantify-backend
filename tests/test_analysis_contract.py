"""Contract tests for AnalysisService (interview/analysis.py).

Verifies the module boundary: AnalysisService reads transcripts, calls LLM,
persists analysis fields, and syncs the legacy interviews table.
All DB/LLM interactions are stubbed.
"""

import json
from pathlib import Path
import sys

import pytest
from flask import Flask, g

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import interview.analysis as analysis_mod
from interview.analysis import AnalysisService
from interview.types import AnalysisResult


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _ToolFunctionStub:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCallStub:
    def __init__(self, name, arguments):
        self.function = _ToolFunctionStub(name, arguments)


class _ResponseMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _ResponseChoice:
    def __init__(self, message):
        self.message = message


class _ResponseStub:
    def __init__(self, tool_calls=None):
        self.choices = [_ResponseChoice(_ResponseMessage(tool_calls=tool_calls))]


def _make_analysis_response(persona="Power User", summary="Engaged and enthusiastic.",
                            sentiment="positive", facts="uses daily;loves features"):
    args = json.dumps({
        "persona_label": persona,
        "findings_summary": summary,
        "sentiment": sentiment,
        "facts": facts,
    })
    return _ResponseStub(tool_calls=[_ToolCallStub("session_analysis", args)])


class _LLMStub:
    call_count = 0
    last_messages = None
    response = None

    def __init__(self, *a, **kw):
        pass

    def getResponse(self, messages, tools=None, tool_choice=None):
        _LLMStub.call_count += 1
        _LLMStub.last_messages = messages
        return _LLMStub.response or _make_analysis_response()


class _DBStub:
    def __init__(self, records=None, respondent_row=None, interview_id=None):
        self._records = list(records or [])
        self._respondent_row = respondent_row
        self._interview_id = interview_id
        self.inserts = []
        self.insert_queries = []

    def query_database_all(self, query, params):
        if "FROM records" in query and "role='user'" in query:
            return [(r,) for r in self._records if r.strip()]
        if "FROM records" in query:
            return [("assistant", "How do you use the app?"),
                    ("user", "I use it every day for tracking"),
                    ("assistant", "What do you like most?"),
                    ("user", "The speed and simplicity are great")]
        return []

    def query_database_one(self, query, params):
        if "FROM respondents" in query:
            return self._respondent_row or (None, None)
        if "FROM interviews" in query:
            return self._interview_id
        return (None,)

    def query_database_insert(self, query, params):
        self.inserts.append((query, params))
        self.insert_queries.append(query)


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        g.projectId = "test_proj"
        g.uuid = "test-user"
        g.llm_purpose = "chat"
        g.llm_service = "core"
        g.baseTopic = "topic_01"
        yield


# ---------------------------------------------------------------------------
# 6B-1: analyze() updates respondent fields
# ---------------------------------------------------------------------------

def test_analysis_updates_respondent_fields(app_ctx, monkeypatch):
    """analyze() must UPDATE respondents with persona_label, findings_summary,
    sentiment, facts, and analyzed_at."""
    _LLMStub.response = _make_analysis_response(
        persona="Power User",
        summary="Engaged daily user.",
        sentiment="positive",
        facts="uses daily;loves speed",
    )
    _LLMStub.call_count = 0
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    db = _DBStub(
        records=["I use it daily", "the speed is great", "yes I love it",
                 "I recommend it to friends", "tracking is my favorite"],
        respondent_row=(None, None),
    )
    svc = AnalysisService(db, "test_proj")
    result = svc.analyze("resp-123")

    assert result.success is True
    assert result.persona_label == "Power User"
    assert result.findings_summary == "Engaged daily user."
    assert result.sentiment == "positive"
    assert result.facts == "uses daily;loves speed"

    update_queries = [q for q, _ in db.inserts if "UPDATE respondents" in q]
    assert len(update_queries) == 1, "Must update respondents table exactly once"

    _, params = next((q, p) for q, p in db.inserts if "UPDATE respondents" in q)
    assert params[0] == "Power User"
    assert params[1] == "Engaged daily user."
    assert params[2] == "positive"
    assert params[3] == "uses daily;loves speed"
    assert "test_proj" in params
    assert "resp-123" in params


# ---------------------------------------------------------------------------
# 6B-2: needs_analysis() returns False for short transcripts
# ---------------------------------------------------------------------------

def test_analysis_skips_short_transcripts(app_ctx, monkeypatch):
    """needs_analysis() must return False when user word count < 5."""
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)
    db = _DBStub(records=["hi", "yes", "no", "ok"])
    svc = AnalysisService(db, "test_proj")

    assert svc.needs_analysis("resp-short") is False


def test_analyze_returns_too_short_for_few_records(app_ctx, monkeypatch):
    """analyze() must return reason='too_short' when < 4 records."""
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    class _SmallDB(_DBStub):
        def query_database_all(self, query, params):
            if "FROM records" in query and "role='user'" not in query:
                return [("user", "hello"), ("assistant", "hi")]
            return super().query_database_all(query, params)

    db = _SmallDB(records=["hello world this is a test"])
    svc = AnalysisService(db, "test_proj")
    result = svc.analyze("resp-tiny")

    assert result.success is False
    assert result.reason == "too_short"


# ---------------------------------------------------------------------------
# 6B-3: analyze() syncs legacy interviews table (update path)
# ---------------------------------------------------------------------------

def test_analysis_syncs_existing_interview_row(app_ctx, monkeypatch):
    """When an interviews row exists, analyze() must UPDATE it."""
    _LLMStub.response = _make_analysis_response()
    _LLMStub.call_count = 0
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    db = _DBStub(
        records=["I use it daily", "the speed is great", "yes I love it",
                 "I recommend it to friends", "tracking is my favorite"],
        respondent_row=(None, None),
        interview_id=("interview-42",),
    )
    svc = AnalysisService(db, "test_proj")
    result = svc.analyze("resp-123")

    assert result.success is True
    interview_updates = [q for q in db.insert_queries if "UPDATE interviews" in q]
    interview_inserts = [q for q in db.insert_queries if "INSERT INTO interviews" in q]
    assert len(interview_updates) == 1, "Must UPDATE existing interviews row"
    assert len(interview_inserts) == 0, "Must NOT INSERT when row exists"


# ---------------------------------------------------------------------------
# 6B-4: analyze() syncs legacy interviews table (insert path)
# ---------------------------------------------------------------------------

def test_analysis_inserts_new_interview_row(app_ctx, monkeypatch):
    """When no interviews row exists, analyze() must INSERT a new one."""
    _LLMStub.response = _make_analysis_response()
    _LLMStub.call_count = 0
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    db = _DBStub(
        records=["I use it daily", "the speed is great", "yes I love it",
                 "I recommend it to friends", "tracking is my favorite"],
        respondent_row=(None, None),
        interview_id=None,
    )
    svc = AnalysisService(db, "test_proj")
    result = svc.analyze("resp-new")

    assert result.success is True
    interview_inserts = [q for q in db.insert_queries if "INSERT INTO interviews" in q]
    interview_updates = [q for q in db.insert_queries if "UPDATE interviews" in q]
    assert len(interview_inserts) == 1, "Must INSERT new interviews row"
    assert len(interview_updates) == 0, "Must NOT UPDATE when no row exists"


# ---------------------------------------------------------------------------
# 6B-5: maybe_analyze() swallows exceptions
# ---------------------------------------------------------------------------

def test_maybe_analyze_swallows_exceptions(app_ctx, monkeypatch):
    """maybe_analyze() must catch and log exceptions, returning None."""
    _LLMStub.call_count = 0
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    class _ExplodingDB(_DBStub):
        def query_database_all(self, query, params):
            if "role='user'" in query:
                return [("enough words to pass the threshold check for analysis",)]
            if "FROM records" in query:
                raise RuntimeError("DB connection lost")
            return []

        def query_database_one(self, query, params):
            if "FROM respondents" in query:
                return (None, None)
            return (None,)

    db = _ExplodingDB()
    svc = AnalysisService(db, "test_proj")
    result = svc.maybe_analyze("resp-boom")

    assert result is None


# ---------------------------------------------------------------------------
# 6B-6: _normalize_args enforces persona_label constraints
# ---------------------------------------------------------------------------

def test_normalize_args_truncates_long_persona():
    """persona_label longer than 4 words must be truncated."""
    args = {
        "persona_label": "Very Long Persona Label That Exceeds Limit",
        "findings_summary": "Summary.",
        "sentiment": "neutral",
        "facts": "fact1",
    }
    persona, summary, sentiment, facts = AnalysisService._normalize_args(args)
    assert len(persona.split()) <= 4


def test_normalize_args_pads_single_word_persona():
    """Single-word persona_label must be padded with 'participant'."""
    args = {
        "persona_label": "Enthusiast",
        "findings_summary": "Summary.",
        "sentiment": "positive",
        "facts": "fact1",
    }
    persona, _, _, _ = AnalysisService._normalize_args(args)
    assert persona == "Enthusiast participant"


def test_normalize_args_defaults_empty_persona():
    """Empty persona_label must default to 'Interview participant'."""
    args = {
        "persona_label": "",
        "findings_summary": "Summary.",
        "sentiment": "neutral",
        "facts": "",
    }
    persona, _, _, _ = AnalysisService._normalize_args(args)
    assert persona == "Interview participant"


# ---------------------------------------------------------------------------
# 6B-7: _build_prompt formats transcript correctly
# ---------------------------------------------------------------------------

def test_build_prompt_formats_roles():
    """_build_prompt must label assistant as Interviewer and user as Participant."""
    records = [
        {"role": "assistant", "content": "What do you think?"},
        {"role": "user", "content": "It's great!"},
    ]
    messages = AnalysisService._build_prompt(records)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "persona_label" in messages[0]["content"]
    assert "Interviewer: What do you think?" in messages[1]["content"]
    assert "Participant: It's great!" in messages[1]["content"]


# ---------------------------------------------------------------------------
# 6B-8: LLM context is restored after analysis
# ---------------------------------------------------------------------------

def test_analysis_restores_llm_context(app_ctx, monkeypatch):
    """After analyze(), g.llm_purpose and g.llm_service must revert."""
    _LLMStub.response = _make_analysis_response()
    _LLMStub.call_count = 0
    monkeypatch.setattr(analysis_mod, "LLM", _LLMStub)

    g.llm_purpose = "chat"
    g.llm_service = "core"

    db = _DBStub(
        records=["I use it daily", "the speed is great", "yes I love it",
                 "I recommend it to friends", "tracking is my favorite"],
        respondent_row=(None, None),
    )
    svc = AnalysisService(db, "test_proj")
    svc.analyze("resp-ctx")

    assert g.llm_purpose == "chat", "llm_purpose must revert after analysis"
    assert g.llm_service == "core", "llm_service must revert after analysis"
