import csv
import io
import logging
from typing import Any, List, Optional
from flask import g

logger = logging.getLogger(__name__)


def _parse_int(value, default: int, min_v: Optional[int] = None, max_v: Optional[int] = None) -> int:
    try:
        n = int(value)
    except Exception:
        n = default
    if min_v is not None:
        n = max(min_v, n)
    if max_v is not None:
        n = min(max_v, n)
    return n


def _coerce_optional_bool(value) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError("Value must be boolean-like")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    raise ValueError("Value must be boolean-like")


class SessionSort:
    DEFAULT = "latest"
    BASE_ORDER = {
        "latest": "a.last_activity_at DESC NULLS LAST, r.created_at DESC",
        "oldest": "a.last_activity_at ASC NULLS LAST, r.created_at ASC",
        "responses_desc": "COALESCE(a.answer_count, 0) DESC, a.last_activity_at DESC NULLS LAST, r.created_at DESC",
        "responses_asc": "COALESCE(a.answer_count, 0) ASC, a.last_activity_at DESC NULLS LAST, r.created_at DESC",
        "external_id_asc": "r.external_id ASC NULLS LAST, a.last_activity_at DESC NULLS LAST, r.created_at DESC",
        "external_id_desc": "r.external_id DESC NULLS LAST, a.last_activity_at DESC NULLS LAST, r.created_at DESC",
    }
    CTE_ORDER = {
        "latest": "s.last_activity_at DESC NULLS LAST, s.created_at DESC",
        "oldest": "s.last_activity_at ASC NULLS LAST, s.created_at ASC",
        "responses_desc": "s.answer_count DESC, s.last_activity_at DESC NULLS LAST, s.created_at DESC",
        "responses_asc": "s.answer_count ASC, s.last_activity_at DESC NULLS LAST, s.created_at DESC",
        "external_id_asc": "s.external_id ASC NULLS LAST, s.last_activity_at DESC NULLS LAST, s.created_at DESC",
        "external_id_desc": "s.external_id DESC NULLS LAST, s.last_activity_at DESC NULLS LAST, s.created_at DESC",
    }

    @staticmethod
    def _resolve_key(filters: dict) -> str:
        raw = (filters.get("sort") or "").strip()
        if raw in SessionSort.BASE_ORDER:
            return raw
        return SessionSort.DEFAULT

    @staticmethod
    def base_order(filters: dict) -> str:
        key = SessionSort._resolve_key(filters)
        return SessionSort.BASE_ORDER[key]

    @staticmethod
    def cte_order(filters: dict) -> str:
        key = SessionSort._resolve_key(filters)
        return SessionSort.CTE_ORDER[key]


class SessionSortResolver:
    DEFAULT = "latest"

    @staticmethod
    def _normalize(value: Optional[str]) -> str:
        if not value:
            return SessionSortResolver.DEFAULT
        return value.strip().lower()

    @staticmethod
    def for_list(value: Optional[str]) -> str:
        key = SessionSortResolver._normalize(value)
        return SessionSortResolver._order_by(key, scope="list")

    @staticmethod
    def for_sessions_cte(value: Optional[str]) -> str:
        key = SessionSortResolver._normalize(value)
        return SessionSortResolver._order_by(key, scope="cte")

    @staticmethod
    def _order_by(key: str, scope: str) -> str:
        if scope == "cte":
            last_activity = "s.last_activity_at"
            created = "s.created_at"
            responses = "COALESCE(s.answer_count, 0)"
            external_id = "LOWER(COALESCE(s.external_id, ''))"
        else:
            last_activity = "a.last_activity_at"
            created = "r.created_at"
            responses = "COALESCE(a.answer_count, 0)"
            external_id = "LOWER(COALESCE(r.external_id, ''))"

        if key in ("", "latest"):
            return f"{last_activity} DESC NULLS LAST, {created} DESC"
        if key == "oldest":
            return f"{last_activity} ASC NULLS LAST, {created} ASC"
        if key == "responses_desc":
            return f"{responses} DESC, {last_activity} DESC NULLS LAST"
        if key == "responses_asc":
            return f"{responses} ASC, {last_activity} DESC NULLS LAST"
        if key == "external_id_asc":
            return f"{external_id} ASC, {last_activity} DESC NULLS LAST"
        if key == "external_id_desc":
            return f"{external_id} DESC, {last_activity} DESC NULLS LAST"
        return f"{last_activity} DESC NULLS LAST, {created} DESC"


def _records_supports_audio() -> bool:
    cached = getattr(g, "_records_supports_audio", None)
    if cached is not None:
        return bool(cached)
    try:
        row = g.db.query_dict_one(
            "SELECT 1 AS ok FROM information_schema.columns WHERE table_name='records' AND column_name='voice_input' LIMIT 1",
            tuple(),
        )
        supported = bool(row)
    except Exception:
        supported = False
    setattr(g, "_records_supports_audio", supported)
    return supported


def _respondents_supports_is_seen() -> bool:
    cached = getattr(g, "_respondents_supports_is_seen", None)
    if cached is not None:
        return bool(cached)
    try:
        row = g.db.query_dict_one(
            "SELECT 1 AS ok FROM information_schema.columns WHERE table_name='respondents' AND column_name='is_seen' LIMIT 1",
            tuple(),
        )
        supported = bool(row)
    except Exception:
        supported = False
    setattr(g, "_respondents_supports_is_seen", supported)
    return supported


def _session_list_query(project_id: str, filters: dict, include_admin_fields: bool, include_match_snippet: bool = True):
    where = ["r.project=%s"]
    params: List[Any] = [project_id]
    include_audio = _records_supports_audio()
    include_is_seen = _respondents_supports_is_seen()

    ext_op = (filters.get("external_id_op") or "").strip()
    ext_val = (filters.get("external_id_val") or "").strip()
    if ext_op == "exists":
        where.append("(r.external_id IS NOT NULL AND r.external_id <> '')")
    elif ext_op == "not_exists":
        where.append("(r.external_id IS NULL OR r.external_id = '')")
    elif ext_op in ("equals", "not_equals") and ext_val:
        where.append(f"(r.external_id {'<>' if ext_op == 'not_equals' else '='} %s)")
        params.append(ext_val)
    elif ext_op in ("contains", "not_contains") and ext_val:
        where.append(f"(r.external_id {'NOT ILIKE' if ext_op == 'not_contains' else 'ILIKE'} %s)")
        params.append(f"%{ext_val}%")

    like_val = filters.get("like")
    if like_val in ("-1", "0", "1"):
        where.append("r.admin_like=%s")
        params.append(int(like_val))

    note_op = (filters.get("note_op") or "").strip()
    note_val = (filters.get("note_val") or "").strip()
    if note_op == "exists":
        where.append("(r.admin_note IS NOT NULL AND r.admin_note <> '')")
    elif note_op == "not_exists":
        where.append("(r.admin_note IS NULL OR r.admin_note = '')")
    elif note_op in ("equals", "not_equals") and note_val:
        where.append(f"(r.admin_note {'<>' if note_op == 'not_equals' else '='} %s)")
        params.append(note_val)
    elif note_op in ("contains", "not_contains") and note_val:
        where.append(f"(r.admin_note {'NOT ILIKE' if note_op == 'not_contains' else 'ILIKE'} %s)")
        params.append(f"%{note_val}%")
    else:
        note_q = (filters.get("note") or "").strip()
        if note_q:
            where.append("(r.admin_note ILIKE %s)")
            params.append(f"%{note_q}%")

    responses_min_raw = (filters.get("responses_min") or "").strip()
    if responses_min_raw:
        try:
            responses_min = int(responses_min_raw)
        except Exception:
            responses_min = None
        if responses_min is not None:
            responses_min = max(0, responses_min)
            where.append("COALESCE(a.answer_count, 0) >= %s")
            params.append(responses_min)

    responses_max_raw = (filters.get("responses_max") or "").strip()
    if responses_max_raw:
        try:
            responses_max = int(responses_max_raw)
        except Exception:
            responses_max = None
        if responses_max is not None:
            responses_max = max(0, responses_max)
            where.append("COALESCE(a.answer_count, 0) <= %s")
            params.append(responses_max)

    hide_seen_raw = (filters.get("hide_seen") or "").strip().lower()
    if include_is_seen and hide_seen_raw in ("1", "true", "yes", "on"):
        where.append("COALESCE(r.is_seen, false) = false")

    if include_audio:
        audio_min_raw = (filters.get("audio_min") or "").strip()
        if audio_min_raw:
            try:
                audio_min = int(audio_min_raw)
            except Exception:
                audio_min = None
            if audio_min is not None:
                audio_min = max(0, audio_min)
                where.append("COALESCE(a.audio_tokens, 0) >= %s")
                params.append(audio_min)

        audio_max_raw = (filters.get("audio_max") or "").strip()
        if audio_max_raw:
            try:
                audio_max = int(audio_max_raw)
            except Exception:
                audio_max = None
            if audio_max is not None:
                audio_max = max(0, audio_max)
                where.append("COALESCE(a.audio_tokens, 0) <= %s")
                params.append(audio_max)

    search = (filters.get("search") or "").strip()
    if search:
        s = f"%{search}%"
        where.append(
            """(
              r.external_id ILIKE %s OR
              r.id::text ILIKE %s OR
              COALESCE(r.persona_label,'') ILIKE %s OR
              COALESCE(r.findings_summary,'') ILIKE %s OR
              COALESCE(i.title,'') ILIKE %s OR
              COALESCE(i.summary,'') ILIKE %s OR
              COALESCE(r.admin_note,'') ILIKE %s OR
              EXISTS (
                SELECT 1 FROM records rr
                WHERE rr.project = r.project AND rr.user_id = r.id
                  AND (rr.content ILIKE %s OR COALESCE(rr.admin_note,'') ILIKE %s)
              )
            )"""
        )
        params.extend([s, s, s, s, s, s, s, s, s])

    snippet_select = "NULL AS match_snippet"
    snippet_params: List[Any] = []
    if search and include_match_snippet:
        snippet_select = """
          (SELECT rr.content
           FROM records rr
           WHERE rr.project = r.project AND rr.user_id = r.id
             AND rr.content ILIKE %s
           ORDER BY rr.created_at ASC
           LIMIT 1) AS match_snippet
        """
        snippet_params.append(s)

    dt_from = (filters.get("from") or "").strip()
    dt_to = (filters.get("to") or "").strip()
    date_where = ""
    date_params: List[Any] = []
    if dt_from:
        date_where += " AND a.last_activity_at >= %s"
        date_params.append(dt_from)
    if dt_to:
        date_where += " AND a.last_activity_at <= %s"
        date_params.append(dt_to)

    select_admin = ""
    if include_admin_fields:
        select_admin = ", r.admin_like, r.admin_note, " + ("COALESCE(r.is_seen, false)" if include_is_seen else "false")

    audio_agg_select = ", 0 AS audio_tokens, 0 AS audio_message_count"
    if include_audio:
        audio_agg_select = ", SUM(COALESCE(audio_tokens, 0)) AS audio_tokens, COUNT(*) FILTER (WHERE voice_input IS TRUE) AS audio_message_count"

    select_audio = ", COALESCE(a.audio_tokens, 0) AS audio_tokens, COALESCE(a.audio_message_count, 0) AS audio_message_count"

    base = f"""
      WITH agg AS (
        SELECT user_id,
               COUNT(*) FILTER (WHERE role='user') AS answer_count,
               MAX(created_at) AS last_activity_at
               {audio_agg_select}
        FROM records
        WHERE project=%s
        GROUP BY user_id
      ),
      last_topic AS (
        SELECT user_id, status
        FROM (
          SELECT user_id, status, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY started_at DESC) AS rn
          FROM topics_log
        ) t
        WHERE rn = 1
      )
      SELECT
        r.id,
        r.created_at,
        r.external_id,
        r.persona_label,
        r.findings_summary,
        {snippet_select},
        COALESCE(a.answer_count, 0) AS answer_count,
        a.last_activity_at,
        CASE WHEN lt.status = 0 THEN true ELSE false END AS is_closed
        {select_audio}
        {select_admin}
      FROM respondents r
      LEFT JOIN agg a ON a.user_id = r.id
      LEFT JOIN last_topic lt ON lt.user_id = r.id
      LEFT JOIN interviews i ON i.project = r.project AND i.respondent = r.id
      WHERE {" AND ".join(where)}
        {date_where}
    """
    all_params: List[Any] = [project_id] + snippet_params + params + date_params
    return base, all_params


def _export_records_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "project_id",
            "project_name",
            "respondent_id",
            "respondent_created_at",
            "external_id",
            "persona_label",
            "findings_summary",
            "record_id",
            "record_role",
            "record_content",
            "record_created_at",
        ]
    )
    for row in rows:
        w.writerow(row)
    return buf.getvalue()


def _export_sessions_csv(rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "respondent_id",
            "created_at",
            "external_id",
            "persona_label",
            "findings_summary",
            "answer_count",
            "last_activity_at",
            "is_closed",
        ]
    )
    for row in rows:
        w.writerow(row)
    return buf.getvalue()
