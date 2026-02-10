import os
import re
import csv
import hashlib
import hmac
import io
import tempfile
import ipaddress
import secrets
from typing import Any, Dict, List, Optional
from flask import Flask, send_from_directory, request, jsonify, g, Response, stream_with_context, session
from flask.views import MethodView
from flask_cors import CORS
import logging

# Import all your existing backend functionality
import openai
from openai import OpenAI
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from llmInterface import LLM
import uuid
import json
from werkzeug.security import check_password_hash, generate_password_hash
from cryptography.fernet import Fernet, InvalidToken
import credentials
from database import DB
from topic import topicHandler
from conversationInterface import conversation
import autoTopic
import platform

if platform.system() == 'Linux':
    from heartbeat import heartbeat
from drawscape_factorio import DrawscapeFactorio

# Create Flask app that serves both frontend and backend
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Signed cookies (share-link auth). Keep secrets in env.local / platform vars only.
class ShareSessionKey:
    @staticmethod
    def resolve():
        primary = os.environ.get("SECRET_KEY") or os.environ.get("FLASK_SECRET_KEY")
        if primary:
            return primary
        # Fallback to a deterministic secret derived from SHARE_LINK_ENC_KEY.
        # This prevents share-link logins from crashing if SECRET_KEY is unset.
        fallback = (os.environ.get("SHARE_LINK_ENC_KEY") or "").strip()
        if fallback:
            return hashlib.sha256(fallback.encode("utf-8")).digest()
        return None


app.secret_key = ShareSessionKey.resolve()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=os.environ.get("SESSION_COOKIE_SAMESITE", "Lax"),
    SESSION_COOKIE_SECURE=(os.environ.get("SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")),
)

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
psycopg2.extras.register_uuid()

# API endpoints that must not require a DB connection
_PUBLIC_API_PATHS = {
    "/api/health",
    "/api/heartbeat/",
    "/api/debug/",
}


def _is_api_request() -> bool:
    return request.path.startswith("/api/")


def _requires_db() -> bool:
    return _is_api_request() and request.path not in _PUBLIC_API_PATHS


def _is_loopback_ip(addr: Optional[str]) -> bool:
    if not addr:
        return False
    try:
        return ipaddress.ip_address(addr).is_loopback
    except Exception:
        return False


def _json_error(message: str, status: int = 400, **extra):
    payload = {"error": message}
    payload.update(extra)
    return jsonify(payload), status


class VoiceFeatureFlag:
    @staticmethod
    def is_enabled(project_id: Optional[str]) -> bool:
        pid = (project_id or "").strip()
        if not pid:
            return False
        db = getattr(g, "db", None)
        if db is None:
            return False
        try:
            row = db.query_database_one("SELECT voice_enabled FROM projects WHERE id=%s LIMIT 1", (pid,))
        except Exception:
            # Backwards-compatible: if the column doesn't exist yet, treat as disabled.
            return False
        return bool(row and row[0])


class VoiceTranscriptionConfig:
    DEFAULT_MODEL = "whisper-1"
    DEFAULT_MAX_BYTES = 15 * 1024 * 1024
    ALLOWED_MIME_TYPES = {
        "audio/flac",
        "audio/mp3",
        "audio/mpeg",
        "audio/mp4",
        "audio/x-m4a",
        "audio/m4a",
        "audio/ogg",
        "audio/wav",
        "audio/webm",
        "audio/x-wav",
        "audio/x-flac",
    }
    ALLOWED_EXTENSIONS = {".flac", ".mp3", ".mp4", ".mpeg", ".m4a", ".ogg", ".wav", ".webm"}

    @staticmethod
    def model() -> str:
        raw = (os.environ.get("VOICE_TRANSCRIPTION_MODEL") or "").strip()
        return raw or VoiceTranscriptionConfig.DEFAULT_MODEL

    @staticmethod
    def max_bytes() -> int:
        raw = (os.environ.get("VOICE_MAX_BYTES") or "").strip()
        try:
            value = int(raw) if raw else VoiceTranscriptionConfig.DEFAULT_MAX_BYTES
        except Exception:
            value = VoiceTranscriptionConfig.DEFAULT_MAX_BYTES
        value = max(1024, value)
        return DrawscapeFactorio.normalize_tokens(value)


class VoiceTranscriptionService:
    @staticmethod
    def _resolve_key(project_id: Optional[str]) -> Optional[str]:
        pid = (project_id or "").strip()
        if pid and pid == credentials.panda_project:
            return credentials.openaiapi_panda_key or credentials.openaiapi_key
        return credentials.openaiapi_key

    @staticmethod
    def _safe_language(raw: Optional[str]) -> Optional[str]:
        if not raw:
            return None
        value = raw.strip().lower()
        if not value:
            return None
        if "-" in value:
            value = value.split("-", 1)[0]
        if len(value) != 2 or not value.isalpha():
            return None
        return value

    @staticmethod
    def _mime_base(value: str) -> str:
        return (value or "").split(";", 1)[0].strip().lower()

    @staticmethod
    def _validate_file(file_storage) -> Optional[str]:
        if not file_storage:
            return "Missing audio file"
        filename = (file_storage.filename or "").strip().lower()
        ext = os.path.splitext(filename)[1]
        content_type = VoiceTranscriptionService._mime_base(file_storage.mimetype or "")
        ext_ok = (not ext) or (ext in VoiceTranscriptionConfig.ALLOWED_EXTENSIONS)
        type_ok = (not content_type) or (content_type in VoiceTranscriptionConfig.ALLOWED_MIME_TYPES)
        if not ext_ok and not type_ok:
            return "Unsupported audio format"
        return None

    @staticmethod
    def _write_temp_audio(data: bytes, ext: str) -> str:
        suffix = ext if ext else ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            return tmp.name

    @staticmethod
    def transcribe(file_storage, project_id: Optional[str], language: Optional[str]):
        err = VoiceTranscriptionService._validate_file(file_storage)
        if err:
            return _json_error(err, 400)

        api_key = VoiceTranscriptionService._resolve_key(project_id)
        if not api_key:
            return _json_error("OpenAI not configured", 500)

        max_bytes = VoiceTranscriptionConfig.max_bytes()
        raw = file_storage.read(max_bytes + 1)
        file_storage.stream.seek(0)
        byte_count = DrawscapeFactorio.normalize_tokens(len(raw))
        if byte_count <= 0:
            return _json_error("Empty audio file", 400)
        if byte_count > max_bytes:
            return _json_error("Audio file too large", 413, max_bytes=max_bytes)

        filename = (file_storage.filename or "").strip().lower()
        ext = os.path.splitext(filename)[1]
        temp_path = VoiceTranscriptionService._write_temp_audio(raw, ext)

        client = OpenAI(api_key=api_key)
        try:
            lang = VoiceTranscriptionService._safe_language(language)
            with open(temp_path, "rb") as audio_file:
                params = {"model": VoiceTranscriptionConfig.model(), "file": audio_file}
                if lang:
                    params["language"] = lang
                response = client.audio.transcriptions.create(**params)
            text = (getattr(response, "text", None) or "").strip()
            return {"text": text}
        except Exception as exc:
            logger.exception("Voice transcription failed: %s", str(exc))
            return _json_error("Transcription failed", 502)
        finally:
            client.close()
            try:
                os.remove(temp_path)
            except Exception:
                pass


class VoiceTranscribeView(MethodView):
    def post(self):
        try:
            project_id = (request.headers.get("projectId") or "").strip()
            user_id = (request.headers.get("uuid") or "").strip()
            if not project_id or not user_id:
                return _json_error("Missing headers: projectId/uuid", 400)

            if not VoiceFeatureFlag.is_enabled(project_id):
                return _json_error("Not found", 404)

            check_if_user_exists()

            file_storage = request.files.get("audio") or request.files.get("file")
            language = request.form.get("language") or request.args.get("language")
            result = VoiceTranscriptionService.transcribe(file_storage, project_id, language)
            if isinstance(result, tuple):
                return result
            return jsonify(result)
        except Exception as exc:
            logger.exception("Voice transcription error: %s", str(exc))
            return _json_error("Transcription failed", 500)


app.add_url_rule(
    "/api/voice-transcribe/",
    view_func=VoiceTranscribeView.as_view("voice_transcribe"),
    methods=["POST"],
)


def _require_internal_key():
    """
    Protect internal-only endpoints (debug/heartbeat) with an env-provided key.

    IMPORTANT:
    - The key must never be hardcoded in the repo.
    - When INTERNAL_API_KEY is unset, these endpoints are effectively disabled.
    """
    expected = (os.environ.get("INTERNAL_API_KEY") or "").strip()
    if not expected:
        # Disabled unless explicitly enabled via env.
        return _json_error("Not enabled", 404)

    provided = (request.args.get("key") or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        return _json_error("Unauthorized", 401)
    return None


def _require_local_admin():
    # Admin is intentionally local-only. This is the main security boundary.
    if not _is_loopback_ip(request.remote_addr):
        return _json_error("Admin is local-only", 403)
    # Admin is enabled only when a local key is configured.
    if not (os.environ.get("ADMIN_LOCAL_KEY") or "").strip():
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
        rows = g.db.query_database_all(q, (project_id,))
        topics = []
        for row in rows:
            topics.append(
                {
                    "id": str(row[0]) if row[0] is not None else None,
                    "project": row[1],
                    "title": row[2],
                    "system": row[3],
                    "group": row[4],
                    "length": int(row[5]) if row[5] is not None else None,
                    "sequence": int(row[6]) if row[6] is not None else None,
                    "topic_type": row[7],
                    "expiration_strategy": row[8],
                    "defined_answers": row[9],
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
        rows = g.db.query_database_all(q, (project_id,))
        logs = []
        for row in rows:
            logs.append(
                {
                    "id": int(row[0]) if row[0] is not None else None,
                    "topic_id": row[1],
                    "user_id": str(row[2]) if row[2] is not None else None,
                    "started_at": row[3].isoformat() if row[3] else None,
                    "status": int(row[4]) if row[4] is not None else None,
                    "responses": int(row[5]) if row[5] is not None else None,
                }
            )
        return jsonify({"logs": logs})


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _require_secret_key_for_sessions():
    if not app.secret_key:
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


def _get_share_cipher() -> Optional[Fernet]:
    key = (os.environ.get("SHARE_LINK_ENC_KEY") or "").strip()
    if not key:
        return None
    try:
        return Fernet(key.encode("utf-8"))
    except Exception:
        return None


def _encrypt_share_value(value: str) -> Optional[str]:
    cipher = _get_share_cipher()
    if not cipher:
        return None
    return cipher.encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_share_value(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cipher = _get_share_cipher()
    if not cipher:
        return None
    try:
        return cipher.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return None


def _share_rate_limited(share_link_id: str, ip: Optional[str]) -> bool:
    # Robust rate limiting: count failed attempts in DB (per link + ip).
    ip_val = (ip or "").strip() or None
    window_minutes = int(os.environ.get("SHARE_LOGIN_RATE_WINDOW_MIN", "15"))
    max_failures = int(os.environ.get("SHARE_LOGIN_RATE_MAX_FAILURES", "8"))
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    q = """
      SELECT COUNT(*) FROM project_share_login_attempts
      WHERE share_link_id=%s AND ip IS NOT DISTINCT FROM %s AND ok=false AND created_at >= %s
    """
    try:
        cnt = g.db.query_database_one(q, (share_link_id, ip_val, since))
        return int(cnt[0]) >= max_failures
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


class SessionInactivityCloser:
    DEFAULT_MINUTES = 10
    MAX_MINUTES = 60 * 24

    @staticmethod
    def _inactive_minutes() -> int:
        raw = (os.environ.get("SESSION_INACTIVITY_MINUTES") or "").strip()
        try:
            minutes = int(raw) if raw else SessionInactivityCloser.DEFAULT_MINUTES
        except Exception:
            minutes = SessionInactivityCloser.DEFAULT_MINUTES
        minutes = max(1, min(minutes, SessionInactivityCloser.MAX_MINUTES))
        return minutes

    @staticmethod
    def _project_id_from_request() -> Optional[str]:
        header_id = (request.headers.get("projectId") or "").strip()
        if header_id:
            return header_id
        path = (request.path or "").strip("/")
        parts = path.split("/")
        if len(parts) >= 4 and parts[0] == "api" and parts[1] == "admin" and parts[2] == "projects":
            return parts[3]
        return None

    @staticmethod
    def close_stale_sessions() -> None:
        if not _requires_db():
            return
        project_id = SessionInactivityCloser._project_id_from_request()
        if not project_id:
            return
        minutes = SessionInactivityCloser._inactive_minutes()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        q = """
          WITH latest AS (
            SELECT tl.user_id, MAX(tl.started_at) AS last_started
            FROM topics_log tl
            JOIN respondents r ON r.id = tl.user_id AND r.project = %s
            WHERE tl.status = 1
            GROUP BY tl.user_id
          ),
          last_input AS (
            SELECT user_id, MAX(created_at) AS last_user_at
            FROM records
            WHERE project=%s AND role='user'
            GROUP BY user_id
          )
          UPDATE topics_log tl
          SET status=0
          FROM latest l
          LEFT JOIN last_input li ON li.user_id = l.user_id
          WHERE tl.user_id = l.user_id
            AND tl.started_at = l.last_started
            AND tl.status = 1
            AND COALESCE(li.last_user_at, tl.started_at) <= %s
        """
        try:
            g.db.query_database_insert(q, (project_id, project_id, cutoff))
        except Exception:
            logger.exception("Failed to close inactive sessions for project %s", project_id)


def _get_share_link_by_token(token: str):
    token_hash = _sha256_hex(token)
    q = """
      SELECT id, project, token_hash, password_hash, allowed_exports, revoked_at, expires_at
      FROM project_share_links
      WHERE token_hash=%s
      LIMIT 1
    """
    row = g.db.query_database_one(q, (token_hash,))
    return token_hash, row


# Import all your existing functions from app.py
def check_if_user_exists():
    query = "SELECT id,project FROM respondents WHERE id=%s"
    query_params = (g.uuid,)
    results = g.db.query_database_one(query,query_params)
    if results and str(results[0]) == g.uuid and str(results[1]) == g.projectId:
        app.logger.info('%s logged in successfully', g.uuid)
        pass
    else:
        app.logger.exception('User not found. Comparing UUID: %s vs %s, Project: %s vs %s', g.uuid, results[0] if results else None, g.projectId, results[1] if results else None)
        raise Exception("Sorry, no user found for this project")

def check_if_project_exists():
    query = "SELECT id FROM projects WHERE id=%s"
    query_params = (g.projectId,)
    results = g.db.query_database_one(query,query_params)
    if results:
        app.logger.info('%s project found successfully', g.projectId)
        pass
    else:
        app.logger.exception('%s project not found', g.projectId)
        raise Exception("Sorry, no project found")

def answerFirstQuestion(answer,ChatGpt,topics):
    chat = get_chat_history(g.uuid,g.projectId)
    store_message(g.uuid,g.projectId,answer,'user',topics[0][4])
    chat.append({"role": "user", "content": answer})
    response = ChatGpt.getResponse(chat)
    message = response.choices[0].message.content
    store_message(g.uuid,g.projectId,message,'assistant',topics[0][4])
    return message

@app.before_request
def get_db():
    # Only initialize DB for API requests that actually require it.
    if not _requires_db():
        return

    if getattr(g, "db", None) is not None:
        return

    try:
        g.db = DB(credentials.get_db_config())
        g.db_error = None
    except Exception as e:
        g.db = None
        # Don't leak secrets; keep message generic.
        g.db_error = str(e)


@app.before_request
def ensure_db_for_api():
    if not _requires_db():
        return
    if getattr(g, "db", None) is None:
        return jsonify(error="Database unavailable", details=getattr(g, "db_error", None)), 503

@app.before_request
def topirHandlerInstance():
    if not _requires_db():
        return
    g.projectId = request.headers.get('projectId')
    g.uuid = request.headers.get('uuid')  # Frontend sends uuid header
    logger.debug(f'UUID received: "{g.uuid}", type: {type(g.uuid)}')
    if g.uuid and g.uuid.strip() != '':
        logger.debug('Creating topic handler for valid UUID')
        g.th = topicHandler() 
        g.baseTopic = g.th.getCurrentTopic()
    else:
        logger.debug('Skipping topic handler - no valid UUID')


@app.before_request
def close_inactive_sessions():
    SessionInactivityCloser.close_stale_sessions()

@app.before_request
def responseCounter():
    if not _requires_db():
        return
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        topics_log = g.th.getTopicsLog()
        if topics_log:	
            g.response_count = topics_log[-1][5]
        else:
            g.response_count = 0

        if request.method == "POST" and request.is_json:
            request_data = request.get_json()
            if 'message' in request_data:
                g.response_count += 1
        logger.debug('===Response Counter (before request):===: %s', g.response_count)
    else:
        g.response_count = 0


@app.before_request
def set_llm_context():
    if not _requires_db():
        return
    # Default LLM usage tagging for core chat flows
    g.llm_purpose = "chat"
    g.llm_service = "core"

@app.before_request
def setglobalvars():
    if not _requires_db():
        return
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        logger.debug('===baseTopic ID (beforere request):===: %s', g.baseTopic)
        g.topic = g.th.switchTopic()
        logger.debug('===Switch ID (beforere request):===: %s', g.topic)

@app.after_request
def updateCounter(response):
    if not _requires_db():
        return response
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        g.th.updateResponseCounter()
    return response


@app.after_request
def add_security_headers(response):
    # Minimal safe headers. Avoid strict CSP globally to not break the existing compiled app.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, 'db', None)
    if db is not None:
        g.db.close()

# Frontend routes - serve React app
@app.route('/')
@app.route('/<path:path>')
def serve_frontend(path=''):
    # --- debug log ---
    try:
        import json as _json
        from datetime import datetime as _dt
        payload = {
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": "H5",
            "location": "server.py:serve_frontend",
            "message": "serve_frontend",
            "data": {"path": path, "request_path": request.path},
            "timestamp": int(_dt.now().timestamp() * 1000),
        }
        with open(
            "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack/.cursor/debug.log",
            "a",
            encoding="utf-8",
        ) as f:
            f.write(_json.dumps(payload) + "\n")
    except Exception:
        pass
    # --- end debug log ---
    if path.startswith('api/'):
        return jsonify(error="Not found"), 404
    if path and os.path.isfile(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')


# Results Portal SPA routes (more specific than Flask's built-in static route).
@app.route("/results", defaults={"path": ""})
@app.route("/results/", defaults={"path": ""})
@app.route("/results/<path:path>")
def serve_results_frontend(path: str):
    results_dir = os.path.join(app.static_folder, "results")
    index_path = os.path.join(results_dir, "index.html")
    if not os.path.isfile(index_path):
        return jsonify(error="Results UI not built"), 404

    # Serve file if it exists (e.g. /results/assets/*)
    if path:
        abs_path = os.path.join(results_dir, path)
        if os.path.isfile(abs_path):
            return send_from_directory(results_dir, path)

    # SPA fallback
    return send_from_directory(results_dir, "index.html")

# Health endpoint (no DB required)
@app.route('/api/health', methods=['GET'])
def health():
    try:
        # Check config is present without opening a connection
        credentials.get_db_config()
        db_configured = True
        db_config_error = None
    except Exception as e:
        db_configured = False
        db_config_error = str(e)

    return jsonify(ok=True, db_required=_requires_db(), db_configured=db_configured, db_config_error=db_config_error), 200

# Backend API routes (with /api prefix)
@app.route('/api/respondent/', methods=['POST'])
def create_respondent():
    project = request.headers.get('projectId')
    external_id = request.headers.get('externalId')
    check_if_project_exists()
    json = request.get_json() or {}
    now = datetime.now(timezone.utc)
    generated_uuid = uuid.uuid4()
    consent_raw = json.get('consent')
    # Frontend may send consent as boolean, string, or even empty string (skip-welcome path).
    # Store a boolean in DB; for non-boolean values assume consent was granted by continuing.
    consent_val = consent_raw if isinstance(consent_raw, bool) else True
    query = "INSERT INTO respondents (id,created_at,project,email,consent,external_id) VALUES (%s,%s,%s,%s,%s,%s)"
    query_params = (generated_uuid,now,project,json.get('email'),consent_val,external_id)
    g.db.query_database_insert(query,query_params)
    return jsonify(uuid=generated_uuid, projectId=project)

@app.route('/api/project/', methods=['GET'])
def get_project():
    project = request.headers.get('projectId')
    query_params = (project,)
    query = None
    labels = None
    try:
        query = "SELECT name,logo,colour,welcome_title,welcome_message,success_title,success_message,abort_title,abort_message,welcome_second_title,welcome_second_message,consent,cta_next,cta_reply,cta_abort,cta_restart,question_title,answer_title,answer_placeholder,loading,collect_email,email_title,email_placeholder,consent_link,skip_welcome,dark_mode,inline_consent,voice_enabled from projects where id=%s"
        labels = [
        "name", "logo", "colour", "welcome_title", "welcome_message",
        "success_title", "success_message", "abort_title", "abort_message",
        "welcome_second_title", "welcome_second_message", "consent", "cta_next",
        "cta_reply", "cta_abort", "cta_restart", "question_title", "answer_title",
        "answer_placeholder", "loading", "collect_email", "email_title",
        "email_placeholder", "consent_link", "skip_welcome", "dark_mode", "inline_consent", "voice_enabled"
        ]
        project_data = g.db.query_database_one(query, query_params)
    except Exception as e:
        logger.warning("Project config missing voice_enabled; treating as disabled: %s", str(e))
        query = "SELECT name,logo,colour,welcome_title,welcome_message,success_title,success_message,abort_title,abort_message,welcome_second_title,welcome_second_message,consent,cta_next,cta_reply,cta_abort,cta_restart,question_title,answer_title,answer_placeholder,loading,collect_email,email_title,email_placeholder,consent_link,skip_welcome,dark_mode,inline_consent from projects where id=%s"
        labels = [
        "name", "logo", "colour", "welcome_title", "welcome_message",
        "success_title", "success_message", "abort_title", "abort_message",
        "welcome_second_title", "welcome_second_message", "consent", "cta_next",
        "cta_reply", "cta_abort", "cta_restart", "question_title", "answer_title",
        "answer_placeholder", "loading", "collect_email", "email_title",
        "email_placeholder", "consent_link", "skip_welcome", "dark_mode", "inline_consent"
        ]
        project_data = g.db.query_database_one(query, query_params)
    if project_data:
        project_dict = {label: value for label, value in zip(labels, project_data)}
        if "voice_enabled" not in project_dict:
            project_dict["voice_enabled"] = False
        return jsonify([project_dict])
    else:
        return jsonify({"error": "Project not found"}), 404

@app.route('/api/reply/', methods=['POST'])
def gpt_response():
    try:
        check_if_user_exists()
        payload = request.get_json() or {}
        user_response = payload.get('message')
        if not isinstance(user_response, str) or not user_response.strip():
            return jsonify(error="Missing JSON field: message"), 400

        # Enable streaming when requested by client
        wants_stream = bool(payload.get("stream")) or ("text/event-stream" in (request.headers.get("Accept") or ""))
        
        logger.debug('Processing reply for user: %s, project: %s', g.uuid, g.projectId)
        logger.debug('baseTopic: %s, topic: %s', getattr(g, 'baseTopic', None), getattr(g, 'topic', None))
        
        chat = conversation(g.th)

        if not wants_stream:
            response = chat.provideResponse(user_response)
            status = chat.retrieveTopicStatus()
            answers = chat.retrieveDefinedAnswers()
            progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
            if status == "closed" and _analysis_needed(g.projectId, g.uuid):
                try:
                    _analyze_and_store(g.projectId, g.uuid)
                except Exception:
                    logger.exception("Auto-analysis failed for %s/%s", g.projectId, g.uuid)
            return jsonify(response=response, status=status, answers=answers, progress=progress)

        # Streaming response (SSE over fetch POST)
        def sse(data: str) -> str:
            return f"data: {data}\n\n"

        def generate():
            prompt_type = g.th.getTopicType(g.topic)
            if prompt_type not in ("prompt", "auto"):
                # For single_question etc, we just return the next assistant message as a single event.
                response_text = chat.provideResponse(user_response)
                final_status = chat.retrieveTopicStatus()
                progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
                yield sse(
                    json.dumps(
                        {
                            "type": "final",
                            "response": response_text,
                            "status": final_status,
                            "answers": chat.retrieveDefinedAnswers(),
                            "progress": progress,
                        }
                    )
                )
                if final_status == "closed" and _analysis_needed(g.projectId, g.uuid):
                    try:
                        _analyze_and_store(g.projectId, g.uuid)
                    except Exception:
                        logger.exception("Auto-analysis failed for %s/%s", g.projectId, g.uuid)
                return

            # Store user message once (matching conversationInterface behavior for prompt/auto)
            g.db.store_message("user", user_response)

            history = chat.retrieveConverasationHistory()
            system_prompt = chat.retrieveTopic() + "\n \n" + chat.getDefaultPrompt()

            # Mirror existing logic: if topic is changing, append+store system prompt
            if getattr(g, 'topicIsChanging', None) is not None:
                history.append({"role": "system", "content": system_prompt})
                chat.DB.store_message("system", system_prompt)

            llm = LLM()
            tools = autoTopic.function if prompt_type == "auto" else None

            full = ""
            tool_call_names = []
            for kind, val in llm.streamResponseOpenAI(history, tools=tools):
                if kind == "delta":
                    full += val
                    yield sse(json.dumps({"type": "delta", "delta": val}))
                elif kind == "tool_call":
                    # We only need function.name to decide whether to switch topic.
                    try:
                        fn = (val.get("function") or {}).get("name")
                        if fn:
                            tool_call_names.append(fn)
                    except Exception:
                        pass

            # Store assistant message
            chat.DB.store_message("assistant", full)

            # Auto topic: if model asked to switch topic, do it and emit the next prompt as final
            if prompt_type == "auto" and tool_call_names:
                # Build a minimal response-like object compatible with autoTopic.switchTopic()
                class _Fn:  # noqa: N801
                    def __init__(self, name): self.name = name
                class _ToolCall:  # noqa: N801
                    def __init__(self, name): self.function = _Fn(name)
                class _Msg:  # noqa: N801
                    def __init__(self, tool_calls): self.tool_calls = tool_calls
                class _Choice:  # noqa: N801
                    def __init__(self, msg): self.message = msg
                class _Resp:  # noqa: N801
                    def __init__(self, choices): self.choices = choices

                fake = _Resp([_Choice(_Msg([_ToolCall(tool_call_names[0])]))])
                switched = autoTopic.switchTopic(fake)
                if switched:
                    # Provide initial response for the next topic
                    next_text = chat.provideInitialResponse()
                    final_status = chat.retrieveTopicStatus()
                    progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
                    yield sse(
                        json.dumps(
                            {
                                "type": "final",
                                "response": next_text,
                                "status": final_status,
                                "answers": chat.retrieveDefinedAnswers(),
                                "progress": progress,
                            }
                        )
                    )
                    if final_status == "closed" and _analysis_needed(g.projectId, g.uuid):
                        try:
                            _analyze_and_store(g.projectId, g.uuid)
                        except Exception:
                            logger.exception("Auto-analysis failed for %s/%s", g.projectId, g.uuid)
                    return
            final_status = chat.retrieveTopicStatus()
            progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
            yield sse(
                json.dumps(
                    {
                        "type": "final",
                        "response": full,
                        "status": final_status,
                        "answers": chat.retrieveDefinedAnswers(),
                        "progress": progress,
                    }
                )
            )
            if final_status == "closed" and _analysis_needed(g.projectId, g.uuid):
                try:
                    _analyze_and_store(g.projectId, g.uuid)
                except Exception:
                    logger.exception("Auto-analysis failed for %s/%s", g.projectId, g.uuid)

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        logger.exception('Error in gpt_response: %s', str(e))
        return jsonify(error=str(e)), 500

@app.route('/api/interview/', methods=['GET'])
def initialize_interview():
    try:
        # --- debug log ---
        try:
            import json as _json
            from datetime import datetime as _dt
            payload = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H3",
                "location": "server.py:initialize_interview",
                "message": "initialize_interview called",
                "data": {
                    "path": request.path,
                    "has_uuid": bool((request.headers.get("uuid") or "").strip()),
                    "has_projectId": bool((request.headers.get("projectId") or "").strip()),
                    "first_answer_present": bool((request.args.get("first_answer") or "").strip()),
                },
                "timestamp": int(_dt.now().timestamp() * 1000),
            }
            with open(
                "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack/.cursor/debug.log",
                "a",
                encoding="utf-8",
            ) as f:
                f.write(_json.dumps(payload) + "\n")
        except Exception:
            pass
        # --- end debug log ---
        check_if_user_exists()
        first_answer = request.args.get('first_answer')
        
        logger.debug('Initializing interview for user: %s, project: %s', g.uuid, g.projectId)
        logger.debug('baseTopic: %s, topic: %s', getattr(g, 'baseTopic', None), getattr(g, 'topic', None))
        
        chat = conversation(g.th)
        if first_answer and getattr(g, 'topicIsChanging', None) is not None:
            logger.info('First answer was provided in GET parameters: %s, for user: %s', first_answer, g.uuid)
            chat.provideInitialResponse()
            g.response_count = 1
            g.baseTopic = g.th.getCurrentTopic()
            g.topic = g.th.switchTopic()
            progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
            response_text = chat.provideResponse(first_answer)
            status = chat.retrieveTopicStatus()
            answers = chat.retrieveDefinedAnswers()
            # --- debug log ---
            try:
                import json as _json
                from datetime import datetime as _dt
                payload = {
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "H3",
                    "location": "server.py:initialize_interview",
                    "message": "initialize_interview first_answer response",
                    "data": {
                        "status": status,
                        "response_len": len(str(response_text or "")),
                        "answers_len": len(answers or []),
                    },
                    "timestamp": int(_dt.now().timestamp() * 1000),
                }
                with open(
                    "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack/.cursor/debug.log",
                    "a",
                    encoding="utf-8",
                ) as f:
                    f.write(_json.dumps(payload) + "\n")
            except Exception:
                pass
            # --- end debug log ---
            return jsonify(response=response_text, status=status, answers=answers, progress=progress)
        response_text = chat.provideInitialResponse()
        status = chat.retrieveTopicStatus()
        answers = chat.retrieveDefinedAnswers()
        progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
        # --- debug log ---
        try:
            import json as _json
            from datetime import datetime as _dt
            payload = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H3",
                "location": "server.py:initialize_interview",
                "message": "initialize_interview response",
                "data": {
                    "status": status,
                    "response_len": len(str(response_text or "")),
                    "answers_len": len(answers or []),
                    "progress": progress,
                },
                "timestamp": int(_dt.now().timestamp() * 1000),
            }
            with open(
                "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack/.cursor/debug.log",
                "a",
                encoding="utf-8",
            ) as f:
                f.write(_json.dumps(payload) + "\n")
        except Exception:
            pass
        # --- end debug log ---
        return jsonify(response=response_text, status=status, answers=answers, progress=progress)
    except Exception as e:
        logger.exception('Error in initialize_interview: %s', str(e))
        # --- debug log ---
        try:
            import json as _json
            from datetime import datetime as _dt
            payload = {
                "sessionId": "debug-session",
                "runId": "run1",
                "hypothesisId": "H3",
                "location": "server.py:initialize_interview",
                "message": "initialize_interview exception",
                "data": {"error": str(e)[:200]},
                "timestamp": int(_dt.now().timestamp() * 1000),
            }
            with open(
                "/Users/nikitashilenok/Documents/vibecoding projects/qvantify-fullstack/.cursor/debug.log",
                "a",
                encoding="utf-8",
            ) as f:
                f.write(_json.dumps(payload) + "\n")
        except Exception:
            pass
        # --- end debug log ---
        return jsonify(error=str(e)), 500

@app.route('/api/quote/', methods=['GET'])
def findClose():
    # text = request.args.get('text')
    # project = request.args.get('projectid')
    # embedding = LLM()
    # vector = embedding.getEmbedding(text,'azure')
    # query = "SELECT id,content,1-(content_v <=> %s::vector) as similarity from records where role='user' AND content_v IS NOT NULL and project=%s ORDER by similarity DESC LIMIT 10"
    # params = (vector,project)
    # ouptut = g.db.query_database_all(query,params)
    # return jsonify(ouptut)
    return jsonify([])

@app.route('/api/heartbeat/', methods=['GET'])
def heartbeat_launch():
    err = _require_internal_key()
    if err:
        return err

    if "heartbeat" not in globals():
        return _json_error("Heartbeat not available on this platform", 501)

    heartbeat()
    return jsonify(status=True)

@app.route('/api/debug/', methods=['GET'])
def debug_info():
    err = _require_internal_key()
    if err:
        return err

    # Validate OpenAI key (tiny request, no secrets returned)
    openai_valid = False
    try:
        if os.environ.get("OPENAI_API_KEY"):
            client = OpenAI()
            _ = client.chat.completions.create(
                model="gpt-5.2",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            client.close()
            openai_valid = True
    except Exception:
        openai_valid = False

    return jsonify(
        {
            "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
            "openai_key_valid": openai_valid,
            "azure_key_set": bool(os.environ.get("AZURE_OPENAI_KEY")),
            "panda_key_set": bool(os.environ.get("OPENAI_PANDA_KEY")),
            "db_config": "configured",
        }
    )

@app.route('/api/alike/interview', methods=['GET'])
def findCloseInterview():
    # text = request.args.get('text')
    # embedding = LLM()
    # vector = embedding.getEmbedding(text,'azure')
    # query = "SELECT respondent,project,title,summary,sentiment,1-(summary_v <=> %s::vector) as similarity from interviews ORDER by similarity DESC LIMIT 10"
    # params = (vector,)
    # ouptut = g.db.query_database_all(query,params)
    # return jsonify(ouptut)
    return jsonify([])

@app.route('/api/topic', methods=['GET'])
def findTopicChanges():
    th = topicHandler()
    ouptut = th.updateResponseCounter()
    return jsonify(ouptut)


# -----------------------------
# Results Portal: Admin (local) + Share links (customer read-only)
# -----------------------------

app.add_url_rule(
    "/api/projects/<project_id>/topics",
    view_func=AdminTopicsView.as_view("admin_topics"),
    methods=["GET"],
)
app.add_url_rule(
    "/api/projects/<project_id>/topics_log",
    view_func=AdminTopicsLogView.as_view("admin_topics_log"),
    methods=["GET"],
)

@app.route("/api/projects", methods=["GET"])
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
    rows = g.db.query_database_all(q, ())
    out = []
    for row in rows:
        out.append(
            {
                "id": row[0],
                "name": row[1],
                "session_count": int(row[2] or 0),
                "last_activity_at": row[3].isoformat() if row[3] else None,
            }
        )
    return jsonify({"projects": out})


@app.route("/api/projects/<project_id>", methods=["GET"])
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
        "temperature",
        "max_tokens",
        "top_p",
        "api",
        "default_prompt",
    ]
    row = None
    try:
        row = g.db.query_database_one(f"SELECT {', '.join(fields)} FROM projects WHERE id=%s LIMIT 1", (project_id,))
    except Exception as e:
        logger.warning("Project config missing max_tokens; falling back to max_completion_tokens: %s", str(e))
        select_fields = [
            "max_completion_tokens AS max_tokens" if field == "max_tokens" else field for field in fields
        ]
        row = g.db.query_database_one(
            f"SELECT {', '.join(select_fields)} FROM projects WHERE id=%s LIMIT 1",
            (project_id,),
        )
    if not row:
        return _json_error("Project not found", 404)
    project = {field: value for field, value in zip(fields, row)}
    return jsonify({"project": project})


@app.route("/api/projects/<project_id>", methods=["PUT"])
def admin_update_project(project_id):
    err = _require_local_admin()
    if err:
        return err
    payload = request.get_json() or {}
    if "voice_enabled" not in payload:
        return _json_error("Missing field: voice_enabled", 400)
    raw_value = payload.get("voice_enabled")
    if isinstance(raw_value, bool):
        enabled = raw_value
    elif isinstance(raw_value, int) and raw_value in (0, 1):
        enabled = bool(raw_value)
    else:
        return _json_error("voice_enabled must be boolean", 400)
    try:
        g.db.query_database_insert("UPDATE projects SET voice_enabled=%s WHERE id=%s", (enabled, project_id))
    except Exception as exc:
        logger.exception("Failed to update voice_enabled for project %s: %s", project_id, str(exc))
        return _json_error("Failed to update project settings", 500)
    return jsonify({"ok": True, "project": {"id": project_id, "voice_enabled": enabled}})


class AdminUsageStats:
    SERVICE_MAP = {
        "core": "interviews",
        "results_portal": "summary",
    }

    @staticmethod
    def _query_usage_rows(project_id: str):
        q = """
          SELECT service, COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) AS tokens
          FROM usage_stats
          WHERE project=%s
          GROUP BY service
        """
        return g.db.query_database_all(q, (project_id,))

    @staticmethod
    def _query_usage_total(project_id: str) -> int:
        q = """
          SELECT COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) AS tokens
          FROM usage_stats
          WHERE project=%s
        """
        row = g.db.query_database_one(q, (project_id,))
        return DrawscapeFactorio.normalize_tokens(row[0] if row else 0)

    @staticmethod
    def _get_usd_rate() -> float:
        raw = (os.environ.get("TOKEN_USD_PER_1K") or "0.01").strip()
        try:
            rate = float(raw)
        except Exception:
            rate = 0.01
        return max(0.0, rate)

    @staticmethod
    def _to_usd(tokens: int, rate: float) -> float:
        return round((float(tokens) / 1000.0) * rate, 2)

    @staticmethod
    def _build_payload(project_id: str, totals: Dict[str, int]):
        rate = AdminUsageStats._get_usd_rate()
        totals_usd = {
            "total": AdminUsageStats._to_usd(totals["total"], rate),
            "interviews": AdminUsageStats._to_usd(totals["interviews"], rate),
            "summary": AdminUsageStats._to_usd(totals["summary"], rate),
            "other": AdminUsageStats._to_usd(totals["other"], rate),
        }
        return {
            "project": {"id": project_id},
            "totals": totals,
            "totals_usd": totals_usd,
            "rate_usd_per_1k": rate,
            "services": [
                {"service": "interviews", "tokens": totals["interviews"]},
                {"service": "summary", "tokens": totals["summary"]},
                {"service": "other", "tokens": totals["other"]},
            ],
        }

    @staticmethod
    def project_usage(project_id):
        err = _require_local_admin()
        if err:
            return err
        totals = {"total": 0, "interviews": 0, "summary": 0, "other": 0}
        try:
            rows = AdminUsageStats._query_usage_rows(project_id)
            for row in rows:
                service = row[0]
                tokens = DrawscapeFactorio.normalize_tokens(row[1])
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


@app.route("/api/projects/<project_id>/usage", methods=["GET"])
def admin_project_usage(project_id):
    return AdminUsageStats.project_usage(project_id)


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


def _session_list_query(project_id: str, filters: dict, include_admin_fields: bool, include_match_snippet: bool = True):
    where = ["r.project=%s"]
    params: List[Any] = [project_id]

    # External ID filtering
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

    # Date range filtering uses last_activity_at from aggregated records.
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
        select_admin = ", r.admin_like, r.admin_note"

    base = f"""
      WITH agg AS (
        SELECT user_id,
               COUNT(*) FILTER (WHERE role='user') AS answer_count,
               MAX(created_at) AS last_activity_at
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
        {select_admin}
      FROM respondents r
      LEFT JOIN agg a ON a.user_id = r.id
      LEFT JOIN last_topic lt ON lt.user_id = r.id
      LEFT JOIN interviews i ON i.project = r.project AND i.respondent = r.id
      WHERE {" AND ".join(where)}
        {date_where}
    """
    all_params: List[Any] = [project_id] + snippet_params + params + date_params  # first %s is agg.project
    return base, all_params


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


@app.route("/api/projects/<project_id>/sessions", methods=["GET"])
def admin_list_sessions(project_id):
    err = _require_local_admin()
    if err:
        return err

    limit = _parse_int(request.args.get("limit"), 50, 1, 200)
    offset = _parse_int(request.args.get("offset"), 0, 0, 10_000)

    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=True, include_match_snippet=True)
    order_by = SessionSortResolver.for_list(request.args.get("sort"))
    q = q_base + f" ORDER BY {order_by} LIMIT %s OFFSET %s"
    rows = g.db.query_database_all(q, tuple(params + [limit, offset]))

    # total count (no pagination)
    q_count = "SELECT COUNT(*) FROM (" + q_base + ") x"
    total = g.db.query_database_one(q_count, tuple(params))[0]

    sessions = []
    for row in rows:
        sessions.append(
            {
                "id": str(row[0]),
                "created_at": row[1].isoformat() if row[1] else None,
                "external_id": row[2],
                "persona_label": row[3],
                "findings_summary": row[4],
                "match_snippet": row[5],
                "answer_count": int(row[6] or 0),
                "last_activity_at": row[7].isoformat() if row[7] else None,
                "is_closed": bool(row[8]),
                "admin_like": int(row[9] or 0),
                "admin_note": row[10],
            }
        )
    return jsonify({"total": int(total or 0), "sessions": sessions})


@app.route("/api/projects/<project_id>/sessions/<respondent_id>", methods=["GET"])
def admin_get_session(project_id, respondent_id):
    err = _require_local_admin()
    if err:
        return err

    include_system = (request.args.get("include_system") or "0") in ("1", "true", "yes")
    q_resp = """
      SELECT id, created_at, external_id, email, consent,
             persona_label, findings_summary, admin_like, admin_note, analyzed_at
      FROM respondents
      WHERE project=%s AND id=%s
      LIMIT 1
    """
    resp_row = g.db.query_database_one(q_resp, (project_id, respondent_id))
    if not resp_row:
        return _json_error("Session not found", 404)

    q_agg = """
      SELECT COUNT(*) FILTER (WHERE role='user') AS answer_count,
             MAX(created_at) AS last_activity_at
      FROM records
      WHERE project=%s AND user_id=%s
    """
    agg_row = g.db.query_database_one(q_agg, (project_id, respondent_id))
    answer_count = int(agg_row[0] or 0) if agg_row else 0
    last_activity_at = agg_row[1] if agg_row else None

    status_row = g.db.query_database_one(
        "SELECT status FROM topics_log WHERE user_id=%s ORDER BY started_at DESC LIMIT 1",
        (respondent_id,),
    )
    is_closed = bool(status_row and status_row[0] == 0)

    # Auto-analyze on demand for closed sessions with missing analysis.
    if is_closed and _analysis_needed(project_id, respondent_id):
        try:
            _analyze_and_store(project_id, respondent_id)
            resp_row = g.db.query_database_one(q_resp, (project_id, respondent_id))
        except Exception:
            logger.exception("On-demand analysis failed for %s/%s", project_id, respondent_id)

    has_record_admin = True
    try:
        q_recs = """
          SELECT r.id, r.created_at, r.role, r.content, r.topic, t.system, t."group", r.admin_like, r.admin_note
          FROM records r
          LEFT JOIN topics t ON t.id = r.topic
          WHERE r.project=%s AND r.user_id=%s
          ORDER BY r.created_at ASC
        """
        rec_rows = g.db.query_database_all(q_recs, (project_id, respondent_id))
    except Exception:
        has_record_admin = False
        q_recs = """
          SELECT r.id, r.created_at, r.role, r.content, r.topic, t.system, t."group"
          FROM records r
          LEFT JOIN topics t ON t.id = r.topic
          WHERE r.project=%s AND r.user_id=%s
          ORDER BY r.created_at ASC
        """
        rec_rows = g.db.query_database_all(q_recs, (project_id, respondent_id))
    records_out = []
    for r in rec_rows:
        if (not include_system) and r[2] == "system":
            continue
        record = {
            "id": str(r[0]),
            "created_at": r[1].isoformat() if r[1] else None,
            "role": r[2],
            "content": r[3],
            "topic": r[4],
            "topic_label": r[5],
            "topic_group": r[6],
        }
        if has_record_admin:
            record["admin_like"] = int(r[7] or 0)
            record["admin_note"] = r[8]
        records_out.append(record)

    proj_row = None
    try:
        q_proj = "SELECT id, name, model, temperature, max_tokens, top_p, api, default_prompt FROM projects WHERE id=%s LIMIT 1"
        proj_row = g.db.query_database_one(q_proj, (project_id,))
    except Exception as e:
        logger.warning("Project config missing max_tokens; falling back to max_completion_tokens: %s", str(e))
        q_proj = "SELECT id, name, model, temperature, max_completion_tokens, top_p, api, default_prompt FROM projects WHERE id=%s LIMIT 1"
        proj_row = g.db.query_database_one(q_proj, (project_id,))
    project_out = None
    if proj_row:
        project_out = {
            "id": proj_row[0],
            "name": proj_row[1],
            "model": proj_row[2],
            "temperature": proj_row[3],
            "max_tokens": proj_row[4],
            "top_p": proj_row[5],
            "api": proj_row[6],
            "default_prompt": proj_row[7],
        }

    return jsonify(
        {
            "session": {
                "id": str(resp_row[0]),
                "created_at": resp_row[1].isoformat() if resp_row[1] else None,
                "external_id": resp_row[2],
                "email": resp_row[3],
                "consent": resp_row[4],
                "persona_label": resp_row[5],
                "findings_summary": resp_row[6],
                "admin_like": int(resp_row[7] or 0),
                "admin_note": resp_row[8],
                "analyzed_at": resp_row[9].isoformat() if resp_row[9] else None,
                "answer_count": answer_count,
                "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
                "is_closed": bool(is_closed),
            },
            "records": records_out,
            "project": project_out,
        }
    )


@app.route("/api/projects/<project_id>/sessions/<respondent_id>/annotation", methods=["PUT"])
def admin_update_session_annotation(project_id, respondent_id):
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

    q = f"UPDATE respondents SET {', '.join(sets)} WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, tuple(params + [project_id, respondent_id]))
    return jsonify({"ok": True})


@app.route("/api/projects/<project_id>/records/<record_id>/annotation", methods=["PUT"])
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
        rows = g.db.query_database_all(q, tuple(params))
        return [str(r[0]) for r in rows]

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


@app.route("/api/projects/<project_id>/sessions/delete", methods=["POST"])
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


@app.route("/api/projects/<project_id>/share_links", methods=["GET", "POST"])
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
        rows = g.db.query_database_all(q, (project_id,))
        links = []
        now = datetime.now(timezone.utc)
        for r in rows:
            token = _decrypt_share_value(r[7])
            password = _decrypt_share_value(r[8])
            share_path = f"/results/share/{token}" if token else None
            share_url = (request.host_url.rstrip("/") + share_path) if share_path else None
            if r[4] is not None:
                status = "revoked"
            elif r[5] is not None and r[5] <= now:
                status = "expired"
            else:
                status = "active"
            links.append(
                {
                    "id": str(r[0]),
                    "label": r[1],
                    "allowed_exports": bool(r[2]),
                    "created_at": r[3].isoformat() if r[3] else None,
                    "revoked_at": r[4].isoformat() if r[4] else None,
                    "expires_at": r[5].isoformat() if r[5] else None,
                    "last_used_at": r[6].isoformat() if r[6] else None,
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
        # 16 chars, URL-safe
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
    link_id = g.db.query_database_one(
        q_ins,
        (project_id, token_hash, password_hash, token_enc, password_enc, label, allowed_exports, expires_at),
    )[0]
    # Ensure the INSERT is committed so the link is visible on subsequent reads.
    try:
        g.db.conn.commit()
    except Exception:
        g.db.conn.rollback()
        raise

    # Return raw token + password exactly once (admin can copy/share).
    share_path = f"/results/share/{token}"
    share_url = request.host_url.rstrip("/") + share_path
    return jsonify({"id": str(link_id), "share_url": share_url, "share_path": share_path, "password": password})


@app.route("/api/projects/<project_id>/share_links/<link_id>/revoke", methods=["POST"])
def admin_revoke_share_link(project_id, link_id):
    err = _require_local_admin()
    if err:
        return err
    q = "UPDATE project_share_links SET revoked_at=now() WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, (project_id, link_id))
    return jsonify({"ok": True})


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


@app.route("/api/projects/<project_id>/export", methods=["GET"])
def admin_export(project_id):
    err = _require_local_admin()
    if err:
        return err

    fmt = (request.args.get("format") or "csv").lower()
    q_base, params = _session_list_query(project_id, request.args, include_admin_fields=False, include_match_snippet=True)
    order_by = SessionSortResolver.for_list(request.args.get("sort"))
    q = q_base + f" ORDER BY {order_by}"
    rows = g.db.query_database_all(q, tuple(params))
    export_rows = []
    for r in rows:
        export_rows.append(
            [
                str(r[0]),
                r[1].isoformat() if r[1] else None,
                r[2],
                r[3],
                r[4],
                int(r[5] or 0),
                r[6].isoformat() if r[6] else None,
                bool(r[7]),
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


def _build_analysis_prompt(records_no_system: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # Keep this short and directly useful for navigation.
    transcript_lines = []
    for m in records_no_system:
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


def _analysis_needed(project_id: str, respondent_id: str) -> bool:
    q_words = "SELECT content FROM records WHERE project=%s AND user_id=%s AND role='user'"
    word_rows = g.db.query_database_all(q_words, (project_id, respondent_id))
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
    row = g.db.query_database_one(q, (project_id, project_id, respondent_id))
    if not row:
        return False
    analyzed_at, last_activity_at = row[0], row[1]
    if analyzed_at is None:
        return True
    if last_activity_at and analyzed_at < last_activity_at:
        return True
    return False


def _analyze_and_store(project_id: str, respondent_id: str):
    # Fetch records (exclude system prompts)
    q = "SELECT role, content FROM records WHERE project=%s AND user_id=%s ORDER BY created_at ASC"
    rows = g.db.query_database_all(q, (project_id, respondent_id))
    records: List[Dict[str, Any]] = [{"role": r[0], "content": r[1]} for r in rows if r[0] != "system"]
    if len(records) < 4:
        return False, "too_short"
    word_count = 0
    for entry in records:
        if entry.get("role") != "user":
            continue
        text = (entry.get("content") or "").strip()
        if not text:
            continue
        word_count += len(re.findall(r"\b\w+\b", text))
    word_count = DrawscapeFactorio.normalize_tokens(word_count)
    if word_count < 5:
        return False, "too_short"

    # Prepare g-context for LLM usage tracking
    prev_purpose = getattr(g, "llm_purpose", None)
    prev_service = getattr(g, "llm_service", None)
    g.projectId = project_id
    g.uuid = respondent_id
    g.baseTopic = getattr(g, "baseTopic", None)
    g.llm_purpose = "analysis"
    g.llm_service = "results_portal"

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

    llm = LLM()
    tool_choice = {"type": "function", "function": {"name": "session_analysis"}}
    resp = llm.getResponse(_build_analysis_prompt(records), tools=tools, tool_choice=tool_choice)
    msg = resp.choices[0].message
    if not getattr(msg, "tool_calls", None):
        return False, "no_tool_call"
    try:
        args = json.loads(msg.tool_calls[0].function.arguments)
    except Exception:
        return False, "bad_tool_args"

    persona_label = (args.get("persona_label") or "").strip()
    findings_summary = (args.get("findings_summary") or "").strip()
    sentiment = (args.get("sentiment") or "").strip()
    facts = (args.get("facts") or "").strip()
    if not persona_label or not findings_summary:
        return False, "missing_fields"
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

    q_upd = """
      UPDATE respondents
      SET persona_label=%s,
          findings_summary=%s,
          analysis_sentiment=%s,
          analysis_facts=%s,
          analyzed_at=now()
      WHERE project=%s AND id=%s
    """
    g.db.query_database_insert(q_upd, (persona_label, findings_summary, sentiment, facts, project_id, respondent_id))
    # Keep legacy interviews table in sync for title/summary usage.
    interview_id = g.db.query_database_one(
        "SELECT id FROM interviews WHERE respondent=%s AND project=%s LIMIT 1",
        (respondent_id, project_id),
    )
    if interview_id:
        q_interview_upd = """
          UPDATE interviews
          SET title=%s,
              summary=%s,
              sentiment=%s,
              facts=%s
          WHERE respondent=%s AND project=%s
        """
        g.db.query_database_insert(
            q_interview_upd,
            (persona_label, findings_summary, sentiment, facts, respondent_id, project_id),
        )
    else:
        q_interview_ins = """
          INSERT INTO interviews (respondent, project, title, summary, sentiment, facts)
          VALUES (%s, %s, %s, %s, %s, %s)
        """
        g.db.query_database_insert(
            q_interview_ins,
            (respondent_id, project_id, persona_label, findings_summary, sentiment, facts),
        )
    # Restore prior LLM tags
    if prev_purpose is None:
        g.llm_purpose = "chat"
    else:
        g.llm_purpose = prev_purpose
    if prev_service is None:
        g.llm_service = "core"
    else:
        g.llm_service = prev_service
    return True, "ok"


@app.route("/api/projects/<project_id>/analyze_stale", methods=["POST"])
def admin_analyze_stale(project_id):
    err = _require_local_admin()
    if err:
        return err

    minutes = _parse_int(request.args.get("inactive_minutes"), 10, 1, 60 * 24)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

    # Eligible if: last activity <= cutoff OR session is closed; and analyzed_at is missing or older than last activity.
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
    rows = g.db.query_database_all(q, (project_id, project_id, cutoff))
    analyzed = 0
    skipped = 0
    details = []
    for (rid,) in rows:
        ok, reason = _analyze_and_store(project_id, str(rid))
        if ok:
            analyzed += 1
        else:
            skipped += 1
        details.append({"respondent_id": str(rid), "ok": ok, "reason": reason})

    return jsonify({"ok": True, "analyzed": analyzed, "skipped": skipped, "details": details})


# -------- Share (customer) --------

@app.route("/api/share/<token>/info", methods=["GET"])
def share_info(token):
    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Not found", 404)
    revoked_at = row[5]
    expires_at = row[6]
    if revoked_at is not None:
        return _json_error("Not found", 404)
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return _json_error("Not found", 404)
    # Minimal public info: project name for nicer login UI.
    proj = g.db.query_database_one("SELECT id, name FROM projects WHERE id=%s LIMIT 1", (row[1],))
    return jsonify({"project": {"id": row[1], "name": proj[1] if proj else None}, "requires_password": True})


@app.route("/api/share/<token>/login", methods=["POST"])
def share_login(token):
    err = _require_secret_key_for_sessions()
    if err:
        return err

    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Invalid link", 404)
    link_id, project_id, _, password_hash, allowed_exports, revoked_at, expires_at = row
    if revoked_at is not None:
        return _json_error("Invalid link", 404)
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
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


def _require_share(token: str):
    err = _require_secret_key_for_sessions()
    if err:
        return err, None
    token_hash, row = _get_share_link_by_token(token)
    if not row:
        return _json_error("Invalid link", 404), None
    link_id, project_id, _, _, allowed_exports, revoked_at, expires_at = row
    if revoked_at is not None:
        return _json_error("Invalid link", 404), None
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        return _json_error("Invalid link", 404), None
    if not _share_session_ok(token_hash):
        return _json_error("Unauthorized", 401), None
    return None, {"link_id": str(link_id), "project_id": project_id, "allowed_exports": bool(allowed_exports)}


@app.route("/api/share/<token>/logout", methods=["POST"])
def share_logout(token):
    err, _ = _require_share(token)
    if err:
        # Still clear any cookie to be safe.
        session.pop("share", None)
        return err
    session.pop("share", None)
    return jsonify({"ok": True})


@app.route("/api/share/<token>/sessions", methods=["GET"])
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
    rows = g.db.query_database_all(q, tuple(params + [limit, offset]))
    q_count = "SELECT COUNT(*) FROM (" + q_base + ") x"
    total = g.db.query_database_one(q_count, tuple(params))[0]

    sessions_out = []
    for row in rows:
        sessions_out.append(
            {
                "id": str(row[0]),
                "created_at": row[1].isoformat() if row[1] else None,
                "external_id": row[2],
                "persona_label": row[3],
                "findings_summary": row[4],
                "match_snippet": row[5],
                "answer_count": int(row[6] or 0),
                "last_activity_at": row[7].isoformat() if row[7] else None,
                "is_closed": bool(row[8]),
                "admin_like": int(row[9] or 0),
                "admin_note": row[10],
            }
        )
    return jsonify({"total": int(total or 0), "sessions": sessions_out, "project": {"id": project_id}})


@app.route("/api/share/<token>/sessions/<respondent_id>", methods=["GET"])
def share_get_session(token, respondent_id):
    err, ctx = _require_share(token)
    if err:
        return err
    project_id = ctx["project_id"]

    q_resp = """
      SELECT id, created_at, external_id, persona_label, findings_summary, analyzed_at, admin_like, admin_note
      FROM respondents
      WHERE project=%s AND id=%s
      LIMIT 1
    """
    resp_row = g.db.query_database_one(q_resp, (project_id, respondent_id))
    if not resp_row:
        return _json_error("Session not found", 404)

    q_recs = """
      SELECT r.id, r.created_at, r.role, r.content, r.topic, t.system, t."group"
      FROM records r
      LEFT JOIN topics t ON t.id = r.topic
      WHERE r.project=%s AND r.user_id=%s AND r.role <> 'system'
      ORDER BY r.created_at ASC
    """
    rec_rows = g.db.query_database_all(q_recs, (project_id, respondent_id))
    records_out = []
    for r in rec_rows:
        records_out.append(
            {
                "id": str(r[0]),
                "created_at": r[1].isoformat() if r[1] else None,
                "role": r[2],
                "content": r[3],
                "topic": r[4],
                "topic_label": r[5],
                "topic_group": r[6],
            }
        )

    proj = g.db.query_database_one("SELECT id, name FROM projects WHERE id=%s LIMIT 1", (project_id,))
    status_row = g.db.query_database_one(
        "SELECT status FROM topics_log WHERE user_id=%s ORDER BY started_at DESC LIMIT 1",
        (respondent_id,),
    )
    is_closed = bool(status_row and status_row[0] == 0)
    return jsonify(
        {
            "session": {
                "id": str(resp_row[0]),
                "created_at": resp_row[1].isoformat() if resp_row[1] else None,
                "external_id": resp_row[2],
                "persona_label": resp_row[3],
                "findings_summary": resp_row[4],
                "analyzed_at": resp_row[5].isoformat() if resp_row[5] else None,
                "admin_like": int(resp_row[6] or 0),
                "admin_note": resp_row[7],
                "is_closed": bool(is_closed),
            },
            "records": records_out,
            "project": {"id": project_id, "name": proj[1] if proj else None},
        }
    )


@app.route("/api/share/<token>/sessions/<respondent_id>/annotation", methods=["PUT"])
def share_update_session_annotation(token, respondent_id):
    err, ctx = _require_share(token)
    if err:
        return err
    project_id = ctx["project_id"]

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

    q = f"UPDATE respondents SET {', '.join(sets)} WHERE project=%s AND id=%s"
    g.db.query_database_insert(q, tuple(params + [project_id, respondent_id]))
    return jsonify({"ok": True})


@app.route("/api/share/<token>/export", methods=["GET"])
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
    rows = g.db.query_database_all(q, tuple(params + [project_id, project_id, project_id]))
    export_rows = []
    for r in rows:
        export_rows.append(
            [
                r[0],
                r[1],
                str(r[2]),
                r[3].isoformat() if r[3] else None,
                r[4],
                r[5],
                r[6],
                str(r[7]),
                r[8],
                r[9],
                r[10].isoformat() if r[10] else None,
            ]
        )

    if fmt == "json":
        return jsonify({"project": project_id, "total": len(export_rows), "rows": export_rows})

    csv_text = _export_records_csv(export_rows)
    return Response(
        csv_text,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename=\"qvantify_{project_id}_export.csv\"'},
    )

def get_chat_history(uuid, project_id):
    query = "SELECT created_at,role,content,topic FROM records WHERE user_id=%s AND project=%s ORDER by created_at ASC"
    query_params = (uuid,project_id)
    results = g.db.query_database_all(query,query_params)
    records = []
    for row in results:
        record_row = (
                row[0],
                row[1],
                row[2],
                row[3]
            )
        records.append(record_row)
    return records

def store_message(uuid, project_id, message, role, topic_id):
    now = datetime.now(timezone.utc)
    query = "INSERT INTO records (created_at,project,role,content,topic,user_id) VALUES (%s,%s,%s,%s,%s,%s)"
    query_params = (now,project_id,role,message,topic_id,uuid)
    g.db.query_database_insert(query,query_params)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
