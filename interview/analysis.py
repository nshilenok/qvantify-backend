"""Interview session analysis service.

Terminal sink: reads transcript, calls LLM, writes analysis result, halts.
Does not trigger any downstream actions.
"""

import json
import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from llmInterface import LLM
from drawscape_factorio import DrawscapeFactorio
from .types import AnalysisResult

logger = logging.getLogger(__name__)


class AnalysisService:
    """Encapsulates respondent session analysis."""

    def __init__(self, db, project_id: str):
        self.db = db
        self.project_id = project_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def needs_analysis(self, respondent_id: str) -> bool:
        """Return True when the respondent has enough data and stale/missing analysis."""
        q_words = "SELECT content FROM records WHERE project=%s AND user_id=%s AND role='user'"
        word_rows = self.db.query_database_all(q_words, (self.project_id, respondent_id))
        word_count = 0
        for (content,) in word_rows:
            text = (content or "").strip()
            if not text:
                continue
            word_count += len(re.findall(r"\b\w+\b", text))
        word_count = DrawscapeFactorio.normalize_tokens(word_count)
        if word_count < 5:
            return False

        q = """
          WITH agg AS (
            SELECT user_id, MAX(created_at) AS last_activity_at
            FROM records
            WHERE project=%s
            GROUP BY user_id
          )
          SELECT r.analyzed_at, a.last_activity_at
          FROM respondents r
          LEFT JOIN agg a ON a.user_id = r.id
          WHERE r.project=%s AND r.id=%s
          LIMIT 1
        """
        row = self.db.query_database_one(q, (self.project_id, self.project_id, respondent_id))
        if not row:
            return False
        analyzed_at, last_activity_at = row[0], row[1]
        if analyzed_at is None:
            return True
        if last_activity_at and analyzed_at < last_activity_at:
            return True
        return False

    def analyze(self, respondent_id: str) -> AnalysisResult:
        """Run LLM analysis on the respondent's transcript and persist the result."""
        records = self._fetch_transcript(respondent_id)
        if len(records) < 4:
            return AnalysisResult(success=False, reason="too_short")

        word_count = self._user_word_count(records)
        if word_count < 5:
            return AnalysisResult(success=False, reason="too_short")

        args = self._call_llm(records, respondent_id)
        if args is None:
            return AnalysisResult(success=False, reason="llm_failed")

        persona_label, findings_summary, sentiment, facts = self._normalize_args(args)
        if not persona_label or not findings_summary:
            return AnalysisResult(success=False, reason="missing_fields")

        self._persist(respondent_id, persona_label, findings_summary, sentiment, facts)

        return AnalysisResult(
            success=True,
            reason="ok",
            persona_label=persona_label,
            findings_summary=findings_summary,
            sentiment=sentiment,
            facts=facts,
        )

    def maybe_analyze(self, respondent_id: str) -> Optional[AnalysisResult]:
        """Convenience: analyze only when needed, swallowing exceptions."""
        if not self.needs_analysis(respondent_id):
            return None
        try:
            return self.analyze(respondent_id)
        except Exception:
            logger.exception("Auto-analysis failed for %s/%s", self.project_id, respondent_id)
            return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch_transcript(self, respondent_id: str) -> List[Dict[str, Any]]:
        q = "SELECT role, content FROM records WHERE project=%s AND user_id=%s ORDER BY created_at ASC"
        rows = self.db.query_database_all(q, (self.project_id, respondent_id))
        return [{"role": r[0], "content": r[1]} for r in rows if r[0] != "system"]

    @staticmethod
    def _user_word_count(records: List[Dict[str, Any]]) -> int:
        word_count = 0
        for entry in records:
            if entry.get("role") != "user":
                continue
            text = (entry.get("content") or "").strip()
            if text:
                word_count += len(re.findall(r"\b\w+\b", text))
        return DrawscapeFactorio.normalize_tokens(word_count)

    def _call_llm(self, records: List[Dict[str, Any]], respondent_id: str) -> Optional[dict]:
        try:
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "session_analysis",
                        "description": "Return a persona label, findings summary, sentiment, and searchable facts.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "persona_label": {"type": "string"},
                                "findings_summary": {"type": "string"},
                                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                                "facts": {"type": "string"},
                            },
                            "required": ["persona_label", "findings_summary", "sentiment", "facts"],
                        },
                    },
                }
            ]
            llm = LLM(db=self.db, project_id=self.project_id)
            tool_choice = {"type": "function", "function": {"name": "session_analysis"}}
            resp = llm.getResponse(self._build_prompt(records), tools=tools, tool_choice=tool_choice)
            msg = resp.choices[0].message
            if not getattr(msg, "tool_calls", None):
                return None
            return json.loads(msg.tool_calls[0].function.arguments)
        except Exception:
            logger.exception("LLM analysis call failed for %s/%s", self.project_id, respondent_id)
            return None

    @staticmethod
    def _build_prompt(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        transcript_lines = []
        for m in records:
            role = m.get("role")
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                transcript_lines.append(f"Interviewer: {content}")
            elif role == "user":
                transcript_lines.append(f"Participant: {content}")
        transcript = "\n".join(transcript_lines)

        return [
            {
                "role": "system",
                "content": (
                    "You analyze interview transcripts for a product team. "
                    "Return a short memorable persona label and a concise findings summary.\n\n"
                    "Rules:\n"
                    "- persona_label: 2-4 words, vivid but professional, no quotes.\n"
                    "- findings_summary: 2-3 sentences, narrative and specific. Avoid phrases like 'this interview'.\n"
                    "- sentiment: one of positive|neutral|negative.\n"
                    "- facts: semicolon-separated key findings for search (max ~8 items).\n"
                ),
            },
            {"role": "user", "content": f"Transcript:\n{transcript}\n\nReturn the analysis now."},
        ]

    @staticmethod
    def _normalize_args(args: dict):
        persona_label = (args.get("persona_label") or "").strip()
        findings_summary = (args.get("findings_summary") or "").strip()
        sentiment = (args.get("sentiment") or "").strip()
        facts = (args.get("facts") or "").strip()

        words = [w for w in persona_label.split() if w]
        if len(words) > 4:
            persona_label = " ".join(words[:4])
        elif len(words) == 1:
            persona_label = f"{words[0]} participant"
        elif len(words) == 0:
            persona_label = "Interview participant"

        if findings_summary:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\\s+", findings_summary) if s.strip()]
            if len(sentences) > 3:
                findings_summary = " ".join(sentences[:3])

        return persona_label, findings_summary, sentiment, facts

    def _persist(self, respondent_id: str, persona_label: str,
                 findings_summary: str, sentiment: str, facts: str) -> None:
        q_upd = """
          UPDATE respondents
          SET persona_label=%s,
              findings_summary=%s,
              analysis_sentiment=%s,
              analysis_facts=%s,
              analyzed_at=now()
          WHERE project=%s AND id=%s
        """
        self.db.query_database_insert(
            q_upd, (persona_label, findings_summary, sentiment, facts, self.project_id, respondent_id)
        )

        interview_id = self.db.query_database_one(
            "SELECT id FROM interviews WHERE respondent=%s AND project=%s LIMIT 1",
            (respondent_id, self.project_id),
        )
        if interview_id:
            q_interview_upd = """
              UPDATE interviews
              SET title=%s, summary=%s, sentiment=%s, facts=%s
              WHERE respondent=%s AND project=%s
            """
            self.db.query_database_insert(
                q_interview_upd,
                (persona_label, findings_summary, sentiment, facts, respondent_id, self.project_id),
            )
        else:
            q_interview_ins = """
              INSERT INTO interviews (respondent, project, title, summary, sentiment, facts)
              VALUES (%s, %s, %s, %s, %s, %s)
            """
            self.db.query_database_insert(
                q_interview_ins,
                (respondent_id, self.project_id, persona_label, findings_summary, sentiment, facts),
            )
