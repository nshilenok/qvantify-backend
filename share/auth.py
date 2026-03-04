import hashlib
import hmac
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta
from flask import g, jsonify, session
from config import cfg

logger = logging.getLogger(__name__)


def _json_error(message: str, status: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_secret_key_for_sessions():
    if not cfg.secret_key:
        return _json_error("Missing SECRET_KEY (required for share-link sessions)", 500)
    return None


def _share_session_ok(token_hash: str) -> bool:
    try:
        s = session.get("share")
        if not isinstance(s, dict):
            return False
        return hmac.compare_digest(str(s.get("token_hash", "")), token_hash)
    except Exception:
        return False


def _share_rate_limited(share_link_id: str, ip: Optional[str]) -> bool:
    ip_val = (ip or "").strip() or None
    window_minutes = cfg.share_login_rate_window_min
    max_failures = cfg.share_login_rate_max_failures
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    q = """
      SELECT COUNT(*) AS cnt FROM project_share_login_attempts
      WHERE share_link_id=%s AND ip IS NOT DISTINCT FROM %s AND ok=false AND created_at >= %s
    """
    try:
        cnt_row = g.db.query_dict_one(q, (share_link_id, ip_val, since))
        return int(cnt_row["cnt"]) >= max_failures
    except Exception as exc:
        logger.warning("Share rate limit check failed: %s", str(exc))
        return False


def _log_share_attempt(share_link_id: str, ip: Optional[str], ok: bool):
    ip_val = (ip or "").strip() or None
    q = "INSERT INTO project_share_login_attempts (share_link_id, ip, ok) VALUES (%s,%s,%s)"
    try:
        g.db.query_database_insert(q, (share_link_id, ip_val, bool(ok)))
    except Exception as exc:
        logger.warning("Share login attempt log failed: %s", str(exc))


def _get_share_link_by_token(token: str):
    token_hash = _sha256_hex(token)
    q = """
      SELECT id, project, token_hash, password_hash, allowed_exports, revoked_at, expires_at
      FROM project_share_links
      WHERE token_hash=%s
      LIMIT 1
    """
    row = g.db.query_dict_one(q, (token_hash,))
    return token_hash, row


def _require_share(token: str):
    err = _require_secret_key_for_sessions()
    if err:
        return err, None
    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Invalid link", 404), None
    if row["revoked_at"] is not None:
        return _json_error("Invalid link", 404), None
    if row["expires_at"] is not None and row["expires_at"] <= datetime.now(timezone.utc):
        return _json_error("Invalid link", 404), None
    if not _share_session_ok(token_hash):
        return _json_error("Unauthorized", 401), None
    return None, {"link_id": str(row["id"]), "project_id": row["project"], "allowed_exports": bool(row["allowed_exports"])}
