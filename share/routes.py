import logging
from datetime import datetime, timezone
from flask import Blueprint, g, request, jsonify, session, Response
from werkzeug.security import check_password_hash
from config import cfg
from share.auth import (
    _json_error,
    _get_share_link_by_token,
    _require_secret_key_for_sessions,
    _share_rate_limited,
    _log_share_attempt,
    _require_share,
)
from admin.session_queries import (
    _parse_int,
    _coerce_optional_bool,
    _session_list_query,
    SessionSortResolver,
    _records_supports_audio,
    _respondents_supports_is_seen,
    _export_records_csv,
)

logger = logging.getLogger(__name__)

share_bp = Blueprint("share", __name__, url_prefix="/api/share")


@share_bp.route("/<token>/info", methods=["GET"])
def share_info(token):
    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Not found", 404)
    if row["revoked_at"] is not None:
        return _json_error("Not found", 404)
    if row["expires_at"] is not None and row["expires_at"] <= datetime.now(timezone.utc):
        return _json_error("Not found", 404)
    proj = g.db.query_dict_one("SELECT id, name FROM projects WHERE id=%s LIMIT 1", (row["project"],))
    return jsonify({"project": {"id": row["project"], "name": proj["name"] if proj else None}, "requires_password": True})


@share_bp.route("/<token>/login", methods=["POST"])
def share_login(token):
    err = _require_secret_key_for_sessions()
    if err:
        return err

    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Invalid link", 404)
    link_id = row["id"]
    project_id = row["project"]
    password_hash = row["password_hash"]
    allowed_exports = row["allowed_exports"]
    if row["revoked_at"] is not None:
        return _json_error("Invalid link", 404)
    if row["expires_at"] is not None and row["expires_at"] <= datetime.now(timezone.utc):
        return _json_error("Invalid link", 404)

    ip = request.remote_addr
    if _share_rate_limited(str(link_id), ip):
        return _json_error("Too many attempts. Try again later.", 429)

    payload = request.get_json() or {}
    password = payload.get("password")
    if not isinstance(password, str) or not password:
        return _json_error("Missing field: password", 400)

    try:
        ok = check_password_hash(password_hash, password)
    except Exception as exc:
        logger.warning("Share login password check failed for link %s: %s", str(link_id), str(exc))
        _log_share_attempt(str(link_id), ip, False)
        return _json_error("Wrong password", 401)
    _log_share_attempt(str(link_id), ip, ok)
    if not ok:
        return _json_error("Wrong password", 401)

    g.db.query_database_insert("UPDATE project_share_links SET last_used_at=now() WHERE id=%s", (link_id,))
    session["share"] = {"token_hash": token_hash, "project": project_id, "allowed_exports": bool(allowed_exports)}
    return jsonify({"ok": True, "project": {"id": project_id}})


@share_bp.route("/<token>/logout", methods=["POST"])
def share_logout(token):
    err, _ = _require_share(token)
    if err:
        session.pop("share", None)
        return err
    session.pop("share", None)
    return jsonify({"ok": True})


@share_bp.route("/<token>/sessions", methods=["GET"])
def share_list_sessions(token):
    err, ctx = _require_share(token)
    if err:
        return err
    project_id = ctx["project_id"]

    limit = _parse_int(request.args.get("limit"), 50, 1, 200)
    offset = _parse_int(request.args.get("offset"), 0, 0, 10_000)

    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=True, include_match_snippet=True)
    order_by = SessionSortResolver.for_list(request.args.get("sort"))
    q = q_base + f" ORDER BY {order_by} LIMIT %s OFFSET %s"
    rows = g.db.query_dict_all(q, tuple(params + [limit, offset]))
    q_count = "SELECT COUNT(*) AS cnt FROM (" + q_base + ") x"
    total_row = g.db.query_dict_one(q_count, tuple(params))
    total = int(total_row["cnt"]) if total_row else 0

    sessions_out = []
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
        sessions_out.append(s)
    return jsonify({"total": total, "sessions": sessions_out, "project": {"id": project_id}})


@share_bp.route("/<token>/sessions/<respondent_id>", methods=["GET"])
def share_get_session(token, respondent_id):
    err, ctx = _require_share(token)
    if err:
        return err
    project_id = ctx["project_id"]

    include_is_seen = _respondents_supports_is_seen()
    q_resp = """
      SELECT id, created_at, external_id, persona_label, findings_summary, analyzed_at, admin_like, admin_note{seen_select}
      FROM respondents
      WHERE project=%s AND id=%s
      LIMIT 1
    """.format(seen_select=", COALESCE(is_seen, false) AS is_seen" if include_is_seen else "")
    resp_row = g.db.query_dict_one(q_resp, (project_id, respondent_id))
    if not resp_row:
        return _json_error("Session not found", 404)

    include_audio = _records_supports_audio()
    q_recs = """
      SELECT r.id, r.created_at, r.role, r.content, r.topic,
             t.system AS topic_label, t."group" AS topic_group,
             {voice_select}
      FROM records r
      LEFT JOIN topics t ON t.id = r.topic
      WHERE r.project=%s AND r.user_id=%s AND r.role <> 'system'
      ORDER BY r.created_at ASC
    """.format(voice_select="r.voice_input, r.audio_tokens" if include_audio else "false AS voice_input, 0 AS audio_tokens")
    rec_rows = g.db.query_dict_all(q_recs, (project_id, respondent_id))
    records_out = []
    for r in rec_rows:
        records_out.append(
            {
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
        )

    proj = g.db.query_dict_one("SELECT id, name FROM projects WHERE id=%s LIMIT 1", (project_id,))
    status_row = g.db.query_dict_one(
        "SELECT status FROM topics_log WHERE user_id=%s ORDER BY started_at DESC LIMIT 1",
        (respondent_id,),
    )
    is_closed = bool(status_row and status_row["status"] == 0)
    return jsonify(
        {
            "session": {
                "id": str(resp_row["id"]),
                "created_at": resp_row["created_at"].isoformat() if resp_row["created_at"] else None,
                "external_id": resp_row["external_id"],
                "persona_label": resp_row["persona_label"],
                "findings_summary": resp_row["findings_summary"],
                "analyzed_at": resp_row["analyzed_at"].isoformat() if resp_row["analyzed_at"] else None,
                "admin_like": int(resp_row["admin_like"] or 0),
                "admin_note": resp_row["admin_note"],
                "is_closed": bool(is_closed),
                "is_seen": bool(resp_row.get("is_seen", False)),
            },
            "records": records_out,
            "project": {"id": project_id, "name": proj["name"] if proj else None},
        }
    )


@share_bp.route("/<token>/sessions/<respondent_id>/annotation", methods=["PUT"])
def share_update_session_annotation(token, respondent_id):
    err, ctx = _require_share(token)
    if err:
        return err
    project_id = ctx["project_id"]

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


@share_bp.route("/<token>/export", methods=["GET"])
def share_export(token):
    err, ctx = _require_share(token)
    if err:
        return err
    if not ctx["allowed_exports"]:
        return _json_error("Export not allowed", 403)
    project_id = ctx["project_id"]

    fmt = (request.args.get("format") or "csv").lower()
    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=False, include_match_snippet=False)
    session_order = SessionSortResolver.for_sessions_cte(request.args.get("sort"))
    q = (
        "WITH sessions AS ("
        + q_base
        + """
        )
        SELECT
          %s AS project_id,
          p.name AS project_name,
          s.id AS respondent_id,
          s.created_at AS respondent_created_at,
          s.external_id,
          s.persona_label,
          s.findings_summary,
          r.id AS record_id,
          r.role AS record_role,
          r.content AS record_content,
          r.created_at AS record_created_at
        FROM sessions s
        JOIN records r ON r.project=%s AND r.user_id = s.id AND r.role <> 'system'
        LEFT JOIN projects p ON p.id = %s
        ORDER BY """
        + session_order
        + """, r.created_at ASC
        """
    )
    rows = g.db.query_dict_all(q, tuple(params + [project_id, project_id, project_id]))
    export_rows = []
    for r in rows:
        export_rows.append(
            [
                r["project_id"],
                r["project_name"],
                str(r["respondent_id"]),
                r["respondent_created_at"].isoformat() if r["respondent_created_at"] else None,
                r["external_id"],
                r["persona_label"],
                r["findings_summary"],
                str(r["record_id"]),
                r["record_role"],
                r["record_content"],
                r["record_created_at"].isoformat() if r["record_created_at"] else None,
            ]
        )

    if fmt == "json":
        return jsonify({"project": project_id, "total": len(export_rows), "rows": export_rows})

    csv_text = _export_records_csv(export_rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="qvantify_{project_id}_export.csv"'},
    )
