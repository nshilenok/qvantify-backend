import ipaddress
import secrets
import logging
from typing import Dict, List, Optional
from flask import Blueprint, g, request, jsonify, Response
from flask.views import MethodView
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash
from config import cfg
from interview.analysis import AnalysisService
from drawscape_factorio import DrawscapeFactorio
from admin.session_queries import (
    _parse_int,
    _coerce_optional_bool,
    _session_list_query,
    SessionSortResolver,
    _records_supports_audio,
    _respondents_supports_is_seen,
    _export_records_csv,
    _export_sessions_csv,
)
from share.crypto import _get_share_cipher, _encrypt_share_value, _decrypt_share_value
from share.auth import _sha256_hex

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/api")


def _json_error(message: str, status: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


def _is_loopback_ip(addr: Optional[str]) -> bool:
    if not addr:
        return False
    try:
        return ipaddress.ip_address(addr).is_loopback
    except Exception:
        return False


def _require_local_admin():
    if not _is_loopback_ip(request.remote_addr):
        return _json_error("Admin is local-only", 403)
    if not cfg.admin_local_key:
        return _json_error("Admin not enabled", 404)
    return None


class AdminTopicsView(MethodView):
    def get(self, project_id):
        err = _require_local_admin()
        if err:
            return err

        q = """
          SELECT id, project, title, system, "group", length, sequence, topic_type, expiration_strategy, defined_answers
          FROM topics
          WHERE project=%s
          ORDER BY sequence ASC
        """
        rows = g.db.query_dict_all(q, (project_id,))
        topics = []
        for row in rows:
            topics.append(
                {
                    "id": str(row["id"]) if row["id"] is not None else None,
                    "project": row["project"],
                    "title": row["title"],
                    "system": row["system"],
                    "group": row["group"],
                    "length": int(row["length"]) if row["length"] is not None else None,
                    "sequence": int(row["sequence"]) if row["sequence"] is not None else None,
                    "topic_type": row["topic_type"],
                    "expiration_strategy": row["expiration_strategy"],
                    "defined_answers": row["defined_answers"],
                }
            )
        return jsonify({"topics": topics})


class AdminTopicsLogView(MethodView):
    def get(self, project_id):
        err = _require_local_admin()
        if err:
            return err

        q = """
          SELECT tl.id, tl.topic_id, tl.user_id, tl.started_at, tl.status, tl.responses
          FROM topics_log tl
          JOIN respondents r ON r.id = tl.user_id
          WHERE r.project=%s
          ORDER BY tl.started_at DESC NULLS LAST, tl.id DESC
        """
        rows = g.db.query_dict_all(q, (project_id,))
        logs = []
        for row in rows:
            logs.append(
                {
                    "id": int(row["id"]) if row["id"] is not None else None,
                    "topic_id": row["topic_id"],
                    "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
                    "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                    "status": int(row["status"]) if row["status"] is not None else None,
                    "responses": int(row["responses"]) if row["responses"] is not None else None,
                }
            )
        return jsonify({"logs": logs})


admin_bp.add_url_rule(
    "/projects/<project_id>/topics",
    view_func=AdminTopicsView.as_view("admin_topics"),
    methods=["GET"],
)
admin_bp.add_url_rule(
    "/projects/<project_id>/topics_log",
    view_func=AdminTopicsLogView.as_view("admin_topics_log"),
    methods=["GET"],
)


@admin_bp.route("/projects", methods=["GET"])
def admin_list_projects():
    err = _require_local_admin()
    if err:
        return err

    q = """
      SELECT
        p.id,
        p.name,
        COALESCE(r.session_count, 0) AS session_count,
        COALESCE(rec.last_activity_at, NULL) AS last_activity_at
      FROM projects p
      LEFT JOIN (
        SELECT project, COUNT(*) AS session_count
        FROM respondents
        GROUP BY project
      ) r ON r.project = p.id
      LEFT JOIN (
        SELECT project, MAX(created_at) AS last_activity_at
        FROM records
        GROUP BY project
      ) rec ON rec.project = p.id
      ORDER BY (rec.last_activity_at IS NULL), rec.last_activity_at DESC, p.name NULLS LAST, p.id
    """
    rows = g.db.query_dict_all(q, ())
    out = []
    for row in rows:
        out.append(
            {
                "id": row["id"],
                "name": row["name"],
                "session_count": int(row["session_count"] or 0),
                "last_activity_at": row["last_activity_at"].isoformat() if row["last_activity_at"] else None,
            }
        )
    return jsonify({"projects": out})


@admin_bp.route("/projects/<project_id>", methods=["GET"])
def admin_get_project(project_id):
    err = _require_local_admin()
    if err:
        return err
    fields = [
        "id",
        "name",
        "logo",
        "colour",
        "welcome_title",
        "welcome_message",
        "success_title",
        "success_message",
        "abort_title",
        "abort_message",
        "welcome_second_title",
        "welcome_second_message",
        "consent",
        "cta_next",
        "cta_reply",
        "cta_abort",
        "cta_restart",
        "question_title",
        "answer_title",
        "answer_placeholder",
        "loading",
        "collect_email",
        "email_title",
        "email_placeholder",
        "consent_link",
        "skip_welcome",
        "dark_mode",
        "inline_consent",
        "voice_enabled",
        "model",
        "reasoning_effort",
        "temperature",
        "max_tokens",
        "top_p",
        "api",
        "default_prompt",
    ]
    row = None
    legacy_fields = [field for field in fields if field != "reasoning_effort"]
    query_attempts = [
        (fields, None),
        (
            ["max_completion_tokens AS max_tokens" if field == "max_tokens" else field for field in fields],
            "Project config missing max_tokens; falling back to max_completion_tokens: %s",
        ),
        (
            legacy_fields,
            "Project config missing reasoning_effort; falling back to legacy columns: %s",
        ),
        (
            ["max_completion_tokens AS max_tokens" if field == "max_tokens" else field for field in legacy_fields],
            "Project config missing max_tokens and reasoning_effort; falling back to max_completion_tokens legacy columns: %s",
        ),
    ]
    for query_fields, warning in query_attempts:
        try:
            row = g.db.query_dict_one(
                f"SELECT {', '.join(query_fields)} FROM projects WHERE id=%s LIMIT 1",
                (project_id,),
            )
            break
        except Exception as exc:
            if warning:
                logger.warning(warning, str(exc))
    if not row:
        return _json_error("Project not found", 404)
    if "reasoning_effort" not in row:
        row["reasoning_effort"] = None
    return jsonify({"project": row})


_PROJECT_TEXT_FIELDS = frozenset({
    "name", "logo", "colour",
    "welcome_title", "welcome_message", "welcome_second_title", "welcome_second_message",
    "success_title", "success_message", "abort_title", "abort_message",
    "consent", "cta_next", "cta_reply", "cta_abort", "cta_restart",
    "question_title", "answer_title", "answer_placeholder", "loading",
    "email_title", "email_placeholder", "consent_link",
    "model", "reasoning_effort", "api", "default_prompt",
})
_PROJECT_BOOL_FIELDS = frozenset({
    "collect_email", "skip_welcome", "dark_mode", "inline_consent", "voice_enabled",
})
_PROJECT_FLOAT_FIELDS = frozenset({"temperature", "top_p"})
_PROJECT_INT_FIELDS = frozenset({"max_tokens"})


def _coerce_project_field(key, value):
    if value is None:
        return None
    if key in _PROJECT_TEXT_FIELDS:
        return str(value)
    if key in _PROJECT_BOOL_FIELDS:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise ValueError(f"{key} must be boolean")
    if key in _PROJECT_FLOAT_FIELDS:
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
    if key in _PROJECT_INT_FIELDS:
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer")
    raise ValueError(f"Unknown field: {key}")


@admin_bp.route("/projects/<project_id>", methods=["PUT"])
def admin_update_project(project_id):
    err = _require_local_admin()
    if err:
        return err
    payload = request.get_json() or {}
    allowed = _PROJECT_TEXT_FIELDS | _PROJECT_BOOL_FIELDS | _PROJECT_FLOAT_FIELDS | _PROJECT_INT_FIELDS
    sets = []
    params = []
    updated = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        try:
            coerced = _coerce_project_field(key, value)
        except ValueError as ve:
            return _json_error(str(ve), 400)
        sets.append(f"{key}=%s")
        params.append(coerced)
        updated[key] = coerced
    if not sets:
        return _json_error("No valid fields to update", 400)
    try:
        q = f"UPDATE projects SET {', '.join(sets)} WHERE id=%s"
        g.db.query_database_insert(q, tuple(params) + (project_id,))
    except Exception as exc:
        logger.exception("Failed to update project %s: %s", project_id, str(exc))
        return _json_error("Failed to update project settings", 500)
    return jsonify({"ok": True, "project": {"id": project_id, **updated}})


class AdminUsageStats:
    SERVICE_MAP = {
        "core": "interviews",
        "results_portal": "summary",
        "audio": "audio",
    }

    @staticmethod
    def _query_usage_rows(project_id: str):
        q = """
          SELECT service, COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) AS tokens
          FROM usage_stats
          WHERE project=%s
          GROUP BY service
        """
        return g.db.query_dict_all(q, (project_id,))

    @staticmethod
    def _query_usage_total(project_id: str) -> int:
        q = """
          SELECT COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) AS tokens
          FROM usage_stats
          WHERE project=%s
        """
        row = g.db.query_dict_one(q, (project_id,))
        return DrawscapeFactorio.normalize_tokens(row["tokens"] if row else 0)

    @staticmethod
    def _to_usd(tokens: int, rate: float) -> float:
        return round((float(tokens) / 1000.0) * rate, 2)

    @staticmethod
    def _build_payload(project_id: str, totals: Dict[str, int]):
        core_rate = cfg.token_usd_per_1k
        audio_rate = cfg.audio_usd_per_1k
        totals_usd = {
            "interviews": AdminUsageStats._to_usd(totals["interviews"], core_rate),
            "summary": AdminUsageStats._to_usd(totals["summary"], core_rate),
            "other": AdminUsageStats._to_usd(totals["other"], core_rate),
            "audio": AdminUsageStats._to_usd(totals["audio"], audio_rate),
        }
        totals_usd["total"] = round(
            totals_usd["interviews"] + totals_usd["summary"] + totals_usd["other"] + totals_usd["audio"], 2
        )
        return {
            "project": {"id": project_id},
            "totals": totals,
            "totals_usd": totals_usd,
            "rate_usd_per_1k": core_rate,
            "rate_usd_per_1k_audio": audio_rate,
            "services": [
                {"service": "interviews", "tokens": totals["interviews"]},
                {"service": "summary", "tokens": totals["summary"]},
                {"service": "audio", "tokens": totals["audio"]},
                {"service": "other", "tokens": totals["other"]},
            ],
        }

    @staticmethod
    def project_usage(project_id):
        err = _require_local_admin()
        if err:
            return err
        totals = {"total": 0, "interviews": 0, "summary": 0, "audio": 0, "other": 0}
        try:
            rows = AdminUsageStats._query_usage_rows(project_id)
            for row in rows:
                service = row["service"]
                tokens = DrawscapeFactorio.normalize_tokens(row["tokens"])
                totals["total"] += tokens
                bucket = DrawscapeFactorio.map_service(service, AdminUsageStats.SERVICE_MAP)
                totals[bucket] += tokens
            return jsonify(AdminUsageStats._build_payload(project_id, totals))
        except Exception:
            logger.exception("Usage stats query failed for project %s", project_id)
        try:
            total = AdminUsageStats._query_usage_total(project_id)
            totals["total"] = total
            totals["interviews"] = total
            return jsonify(AdminUsageStats._build_payload(project_id, totals))
        except Exception:
            logger.exception("Usage stats total query failed for project %s", project_id)
            return jsonify(AdminUsageStats._build_payload(project_id, totals))


@admin_bp.route("/projects/<project_id>/usage", methods=["GET"])
def admin_project_usage(project_id):
    return AdminUsageStats.project_usage(project_id)


@admin_bp.route("/projects/<project_id>/sessions", methods=["GET"])
def admin_list_sessions(project_id):
    err = _require_local_admin()
    if err:
        return err

    limit = _parse_int(request.args.get("limit"), 50, 1, 200)
    offset = _parse_int(request.args.get("offset"), 0, 0, 10_000)

    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=True, include_match_snippet=True)
    order_by = SessionSortResolver.for_list(request.args.get("sort"))
    q = q_base + f" ORDER BY {order_by} LIMIT %s OFFSET %s"
    rows = g.db.query_dict_all(q, tuple(params + [limit, offset]))

    q_count = "SELECT COUNT(*) AS cnt FROM (" + q_base + ") x"
    total_row = g.db.query_dict_one(q_count, tuple(params))
    total = int(total_row["cnt"]) if total_row else 0

    sessions = []
    for row in rows:
        s = {
            "id": str(row["id"]),
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "external_id": row["external_id"],
            "persona_label": row["persona_label"],
            "findings_summary": row["findings_summary"],
            "match_snippet": row["match_snippet"],
            "answer_count": int(row["answer_count"] or 0),
            "last_activity_at": row["last_activity_at"].isoformat() if row["last_activity_at"] else None,
            "is_closed": bool(row["is_closed"]),
            "audio_tokens": int(row.get("audio_tokens") or 0),
            "audio_message_count": int(row.get("audio_message_count") or 0),
        }
        if "admin_like" in row:
            s["admin_like"] = int(row["admin_like"] or 0)
        if "admin_note" in row:
            s["admin_note"] = row["admin_note"]
        if "is_seen" in row:
            s["is_seen"] = bool(row["is_seen"])
        else:
            s["is_seen"] = False
        sessions.append(s)
    return jsonify({"total": total, "sessions": sessions})


@admin_bp.route("/projects/<project_id>/sessions/<respondent_id>", methods=["GET"])
def admin_get_session(project_id, respondent_id):
    err = _require_local_admin()
    if err:
        return err

    include_system = (request.args.get("include_system") or "0") in ("1", "true", "yes")
    include_is_seen = _respondents_supports_is_seen()
    q_resp = """
      SELECT id, created_at, external_id, email, consent,
             persona_label, findings_summary, admin_like, admin_note, analyzed_at{seen_select}
      FROM respondents
      WHERE project=%s AND id=%s
      LIMIT 1
    """.format(seen_select=", COALESCE(is_seen, false) AS is_seen" if include_is_seen else "")
    resp_row = g.db.query_dict_one(q_resp, (project_id, respondent_id))
    if not resp_row:
        return _json_error("Session not found", 404)

    q_agg = """
      SELECT COUNT(*) FILTER (WHERE role='user') AS answer_count,
             MAX(created_at) AS last_activity_at
      FROM records
      WHERE project=%s AND user_id=%s
    """
    agg_row = g.db.query_dict_one(q_agg, (project_id, respondent_id))
    answer_count = int(agg_row["answer_count"] or 0) if agg_row else 0
    last_activity_at = agg_row["last_activity_at"] if agg_row else None

    status_row = g.db.query_dict_one(
        "SELECT status FROM topics_log WHERE user_id=%s ORDER BY started_at DESC LIMIT 1",
        (respondent_id,),
    )
    is_closed = bool(status_row and status_row["status"] == 0)

    _analysis_svc = AnalysisService(g.db, project_id)
    if is_closed and _analysis_svc.needs_analysis(respondent_id):
        try:
            _analysis_svc.analyze(respondent_id)
            resp_row = g.db.query_dict_one(q_resp, (project_id, respondent_id))
        except Exception:
            logger.exception("On-demand analysis failed for %s/%s", project_id, respondent_id)

    include_audio = _records_supports_audio()
    has_record_admin = True
    try:
        q_recs = """
          SELECT r.id, r.created_at, r.role, r.content, r.topic,
                 t.system AS topic_label, t."group" AS topic_group,
                 r.admin_like, r.admin_note,
                 {voice_select}
          FROM records r
          LEFT JOIN topics t ON t.id = r.topic
          WHERE r.project=%s AND r.user_id=%s
          ORDER BY r.created_at ASC
        """.format(
            voice_select="r.voice_input, r.audio_tokens" if include_audio else "false AS voice_input, 0 AS audio_tokens"
        )
        rec_rows = g.db.query_dict_all(q_recs, (project_id, respondent_id))
    except Exception:
        has_record_admin = False
        q_recs = """
          SELECT r.id, r.created_at, r.role, r.content, r.topic,
                 t.system AS topic_label, t."group" AS topic_group,
                 {voice_select}
          FROM records r
          LEFT JOIN topics t ON t.id = r.topic
          WHERE r.project=%s AND r.user_id=%s
          ORDER BY r.created_at ASC
        """.format(
            voice_select="r.voice_input, r.audio_tokens" if include_audio else "false AS voice_input, 0 AS audio_tokens"
        )
        rec_rows = g.db.query_dict_all(q_recs, (project_id, respondent_id))
    records_out = []
    for r in rec_rows:
        if (not include_system) and r["role"] == "system":
            continue
        record = {
            "id": str(r["id"]),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "role": r["role"],
            "content": r["content"],
            "topic": r["topic"],
            "topic_label": r["topic_label"],
            "topic_group": r["topic_group"],
            "voice_input": bool(r.get("voice_input")),
            "audio_tokens": int(r.get("audio_tokens") or 0),
        }
        if has_record_admin:
            record["admin_like"] = int(r.get("admin_like") or 0)
            record["admin_note"] = r.get("admin_note")
        records_out.append(record)

    project_fields = [
        "id", "name", "model", "reasoning_effort", "temperature",
        "max_tokens", "top_p", "api", "default_prompt",
    ]
    legacy_project_fields = [f for f in project_fields if f != "reasoning_effort"]
    project_query_attempts = [
        (project_fields, None),
        (
            ["max_completion_tokens AS max_tokens" if f == "max_tokens" else f for f in project_fields],
            "Project config missing max_tokens; falling back to max_completion_tokens: %s",
        ),
        (
            legacy_project_fields,
            "Project config missing reasoning_effort; falling back to legacy columns: %s",
        ),
        (
            ["max_completion_tokens AS max_tokens" if f == "max_tokens" else f for f in legacy_project_fields],
            "Project config missing max_tokens and reasoning_effort; falling back to max_completion_tokens legacy columns: %s",
        ),
    ]
    project_out = None
    for query_fields, warning in project_query_attempts:
        try:
            project_out = g.db.query_dict_one(
                f"SELECT {', '.join(query_fields)} FROM projects WHERE id=%s LIMIT 1",
                (project_id,),
            )
            break
        except Exception as exc:
            if warning:
                logger.warning(warning, str(exc))
    if project_out and "reasoning_effort" not in project_out:
        project_out["reasoning_effort"] = None

    return jsonify(
        {
            "session": {
                "id": str(resp_row["id"]),
                "created_at": resp_row["created_at"].isoformat() if resp_row["created_at"] else None,
                "external_id": resp_row["external_id"],
                "email": resp_row["email"],
                "consent": resp_row["consent"],
                "persona_label": resp_row["persona_label"],
                "findings_summary": resp_row["findings_summary"],
                "admin_like": int(resp_row["admin_like"] or 0),
                "admin_note": resp_row["admin_note"],
                "analyzed_at": resp_row["analyzed_at"].isoformat() if resp_row["analyzed_at"] else None,
                "answer_count": answer_count,
                "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
                "is_closed": bool(is_closed),
                "is_seen": bool(resp_row.get("is_seen", False)),
            },
            "records": records_out,
            "project": project_out,
        }
    )


@admin_bp.route("/projects/<project_id>/sessions/<respondent_id>/annotation", methods=["PUT"])
def admin_update_session_annotation(project_id, respondent_id):
    err = _require_local_admin()
    if err:
        return err

    payload = request.get_json() or {}
    admin_note = payload.get("admin_note")
    admin_like = payload.get("admin_like")
    is_seen = payload.get("is_seen")
    include_is_seen = _respondents_supports_is_seen()
    if admin_like is not None:
        try:
            admin_like = int(admin_like)
        except Exception:
            return _json_error("admin_like must be -1, 0, or 1", 400)
        if admin_like not in (-1, 0, 1):
            return _json_error("admin_like must be -1, 0, or 1", 400)
    if is_seen is not None:
        if not include_is_seen:
            return _json_error("is_seen is not supported by current database schema", 400)
        try:
            is_seen = _coerce_optional_bool(is_seen)
        except ValueError:
            return _json_error("is_seen must be a boolean", 400)

    sets = []
    params = []
    if admin_note is not None:
        sets.append("admin_note=%s")
        params.append(str(admin_note) if admin_note is not None else None)
    if admin_like is not None:
        sets.append("admin_like=%s")
        params.append(admin_like)
    if is_seen is not None:
        sets.append("is_seen=%s")
        params.append(bool(is_seen))
    if not sets:
        return _json_error("No fields to update", 400)

    q = f"UPDATE respondents SET {', '.join(sets)} WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, tuple(params + [project_id, respondent_id]))
    return jsonify({"ok": True})


@admin_bp.route("/projects/<project_id>/records/<record_id>/annotation", methods=["PUT"])
def admin_update_record_annotation(project_id, record_id):
    err = _require_local_admin()
    if err:
        return err

    payload = request.get_json() or {}
    admin_note = payload.get("admin_note")
    admin_like = payload.get("admin_like")
    if admin_like is not None:
        try:
            admin_like = int(admin_like)
        except Exception:
            return _json_error("admin_like must be -1, 0, or 1", 400)
        if admin_like not in (-1, 0, 1):
            return _json_error("admin_like must be -1, 0, or 1", 400)

    sets = []
    params = []
    if admin_note is not None:
        sets.append("admin_note=%s")
        params.append(str(admin_note) if admin_note is not None else None)
    if admin_like is not None:
        sets.append("admin_like=%s")
        params.append(admin_like)
    if not sets:
        return _json_error("No fields to update", 400)

    q = f"UPDATE records SET {', '.join(sets)} WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, tuple(params + [project_id, record_id]))
    return jsonify({"ok": True})


class AdminSessionDeletion:
    MAX_IDS = 20000

    @staticmethod
    def _dedupe_ids(values):
        if not isinstance(values, list):
            return []
        cleaned = []
        seen = set()
        for val in values:
            if not isinstance(val, str):
                continue
            trimmed = val.strip()
            if not trimmed or trimmed in seen:
                continue
            seen.add(trimmed)
            cleaned.append(trimmed)
        return cleaned

    @staticmethod
    def _normalize_filters(raw_filters):
        if not isinstance(raw_filters, dict):
            return {}
        normalized = {}
        for key, value in raw_filters.items():
            if value is None:
                continue
            normalized[str(key)] = str(value)
        return normalized

    @staticmethod
    def _ids_from_filters(project_id: str, filters: dict, exclude_ids: List[str]):
        q_base, params = _session_list_query(project_id, filters, include_admin_fields=False, include_match_snippet=False)
        q = f"SELECT id FROM ({q_base}) s"
        if exclude_ids:
            q += " WHERE id NOT IN %s"
            params = params + [tuple(exclude_ids)]
        rows = g.db.query_dict_all(q, tuple(params))
        return [str(r["id"]) for r in rows]

    @staticmethod
    def delete(project_id: str, respondent_ids: List[str]) -> int:
        if not respondent_ids:
            return 0
        if len(respondent_ids) > AdminSessionDeletion.MAX_IDS:
            raise ValueError("Too many sessions selected")
        ids_tuple = tuple(respondent_ids)
        conn = g.db.conn
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM records WHERE project=%s AND user_id IN %s", (project_id, ids_tuple))
            cur.execute("DELETE FROM topics_log WHERE user_id IN %s", (ids_tuple,))
            cur.execute("DELETE FROM usage_stats WHERE project=%s AND user_id IN %s", (project_id, ids_tuple))
            cur.execute("DELETE FROM interviews_sentences WHERE project=%s AND respondent IN %s", (project_id, ids_tuple))
            cur.execute("DELETE FROM interviews WHERE project=%s AND respondent IN %s", (project_id, ids_tuple))
            cur.execute("DELETE FROM respondents WHERE project=%s AND id IN %s", (project_id, ids_tuple))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
        return DrawscapeFactorio.normalize_tokens(len(respondent_ids))


@admin_bp.route("/projects/<project_id>/sessions/delete", methods=["POST"])
def admin_delete_sessions(project_id):
    err = _require_local_admin()
    if err:
        return err

    payload = request.get_json() or {}
    select_all = bool(payload.get("select_all"))
    exclude_ids = AdminSessionDeletion._dedupe_ids(payload.get("exclude_ids"))
    filters = AdminSessionDeletion._normalize_filters(payload.get("filters"))
    ids = AdminSessionDeletion._dedupe_ids(payload.get("ids"))

    if select_all:
        ids = AdminSessionDeletion._ids_from_filters(project_id, filters, exclude_ids)

    if not ids:
        return jsonify({"ok": True, "deleted": 0})
    try:
        deleted = AdminSessionDeletion.delete(project_id, ids)
    except ValueError as e:
        return _json_error(str(e), 400)

    return jsonify({"ok": True, "deleted": deleted})


@admin_bp.route("/projects/<project_id>/share_links", methods=["GET", "POST"])
def admin_share_links(project_id):
    err = _require_local_admin()
    if err:
        return err

    if request.method == "GET":
        if not _get_share_cipher():
            return _json_error("Missing SHARE_LINK_ENC_KEY", 500)
        q = """
          SELECT id, label, allowed_exports, created_at, revoked_at, expires_at, last_used_at, token_enc, password_enc
          FROM project_share_links
          WHERE project=%s
          ORDER BY created_at DESC
        """
        rows = g.db.query_dict_all(q, (project_id,))
        links = []
        now = datetime.now(timezone.utc)
        for r in rows:
            token = _decrypt_share_value(r["token_enc"])
            password = _decrypt_share_value(r["password_enc"])
            share_path = f"/results/share/{token}" if token else None
            share_url = (request.host_url.rstrip("/") + share_path) if share_path else None
            if r["revoked_at"] is not None:
                status = "revoked"
            elif r["expires_at"] is not None and r["expires_at"] <= now:
                status = "expired"
            else:
                status = "active"
            links.append(
                {
                    "id": str(r["id"]),
                    "label": r["label"],
                    "allowed_exports": bool(r["allowed_exports"]),
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    "revoked_at": r["revoked_at"].isoformat() if r["revoked_at"] else None,
                    "expires_at": r["expires_at"].isoformat() if r["expires_at"] else None,
                    "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
                    "status": status,
                    "share_url": share_url,
                    "share_path": share_path,
                    "password": password,
                }
            )
        return jsonify({"links": links})

    payload = request.get_json() or {}
    label = (payload.get("label") or "").strip() or None
    allowed_exports = bool(payload.get("allowed_exports", True))
    password = payload.get("password")
    if not password:
        password = secrets.token_urlsafe(12)
    token = secrets.token_urlsafe(32)
    token_hash = _sha256_hex(token)
    password_hash = generate_password_hash(str(password), method="pbkdf2:sha256")
    token_enc = _encrypt_share_value(token)
    password_enc = _encrypt_share_value(str(password))
    if not token_enc or not password_enc:
        return _json_error("Missing SHARE_LINK_ENC_KEY", 500)

    expires_at = payload.get("expires_at")
    q_ins = """
      INSERT INTO project_share_links (project, token_hash, password_hash, token_enc, password_enc, label, allowed_exports, expires_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
      RETURNING id
    """
    link_row = g.db.query_dict_one(
        q_ins,
        (project_id, token_hash, password_hash, token_enc, password_enc, label, allowed_exports, expires_at),
    )
    link_id = link_row["id"]
    try:
        g.db.conn.commit()
    except Exception:
        g.db.conn.rollback()
        raise

    share_path = f"/results/share/{token}"
    share_url = request.host_url.rstrip("/") + share_path
    return jsonify({"id": str(link_id), "share_url": share_url, "share_path": share_path, "password": password})


@admin_bp.route("/projects/<project_id>/share_links/<link_id>/revoke", methods=["POST"])
def admin_revoke_share_link(project_id, link_id):
    err = _require_local_admin()
    if err:
        return err
    q = "UPDATE project_share_links SET revoked_at=now() WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, (project_id, link_id))
    return jsonify({"ok": True})


@admin_bp.route("/projects/<project_id>/export", methods=["GET"])
def admin_export(project_id):
    err = _require_local_admin()
    if err:
        return err

    fmt = (request.args.get("format") or "csv").lower()
    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=False, include_match_snippet=True)
    order_by = SessionSortResolver.for_list(request.args.get("sort"))
    q = q_base + f" ORDER BY {order_by}"
    rows = g.db.query_dict_all(q, tuple(params))
    export_rows = []
    for r in rows:
        export_rows.append(
            [
                str(r["id"]),
                r["created_at"].isoformat() if r["created_at"] else None,
                r["external_id"],
                r["persona_label"],
                r["findings_summary"],
                int(r.get("answer_count") or 0),
                r["last_activity_at"].isoformat() if r["last_activity_at"] else None,
                bool(r["is_closed"]),
            ]
        )

    if fmt == "json":
        return jsonify({"project": project_id, "total": len(export_rows), "rows": export_rows})

    csv_text = _export_sessions_csv(export_rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="qvantify_{project_id}_export.csv"'},
    )


@admin_bp.route("/projects/<project_id>/analyze_stale", methods=["POST"])
def admin_analyze_stale(project_id):
    err = _require_local_admin()
    if err:
        return err

    minutes = _parse_int(request.args.get("inactive_minutes"), 10, 1, 60 * 24)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    q = """
      WITH agg AS (
        SELECT user_id, MAX(created_at) AS last_activity_at
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
      SELECT r.id
      FROM respondents r
      LEFT JOIN agg a ON a.user_id = r.id
      LEFT JOIN last_topic lt ON lt.user_id = r.id
      WHERE r.project=%s
        AND (
          a.last_activity_at <= %s OR (lt.status = 0)
        )
        AND (
          r.analyzed_at IS NULL OR (a.last_activity_at IS NOT NULL AND r.analyzed_at < a.last_activity_at)
        )
      ORDER BY a.last_activity_at DESC NULLS LAST
      LIMIT 50
    """
    rows = g.db.query_dict_all(q, (project_id, project_id, cutoff))
    _stale_svc = AnalysisService(g.db, project_id)
    analyzed = 0
    skipped = 0
    details = []
    for row in rows:
        rid = row["id"]
        result = _stale_svc.analyze(str(rid))
        if result.success:
            analyzed += 1
        else:
            skipped += 1
        details.append({"respondent_id": str(rid), "ok": result.success, "reason": result.reason})

    return jsonify({"ok": True, "analyzed": analyzed, "skipped": skipped, "details": details})
