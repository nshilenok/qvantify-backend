import os
import hmac
import tempfile
from typing import Any, Dict, List, Optional
from flask import Flask, request, jsonify, g, Response, stream_with_context
from flask.views import MethodView
from flask_cors import CORS
import logging

import openai
from openai import OpenAI
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
import uuid
import json
import credentials
from config import AppConfig, cfg
from database import DB
from interview.topic_engine import TopicEngine as topicHandler
from interview.conversation import conversation
import platform

from interview.context import RequestContext
from interview.types import ReplyInput
from interview.reply_handler import ReplyHandler, _build_reply_debug
from interview.analysis import AnalysisService
from interview.session_closer import SessionInactivityCloser

if platform.system() == 'Linux':
    from heartbeat import heartbeat

from admin import admin_bp
from share import share_bp

APP_VERSION = cfg.app_version

# Create Flask app for backend API only
app = Flask(__name__)
CORS(app)

app.secret_key = cfg.secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE=cfg.session_cookie_samesite,
    SESSION_COOKIE_SECURE=cfg.session_cookie_secure,
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
            row = db.query_dict_one("SELECT voice_enabled FROM projects WHERE id=%s LIMIT 1", (pid,))
        except Exception:
            return False
        return bool(row and row["voice_enabled"])


class VoiceTranscriptionConfig:
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
        return cfg.voice_transcription_model

    @staticmethod
    def max_bytes() -> int:
        return DrawscapeFactorio.normalize_tokens(cfg.voice_max_bytes)


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
        audio_tokens = DrawscapeFactorio.normalize_tokens(byte_count)
        if audio_tokens <= 0:
            return _json_error("Empty audio file", 400)
        if audio_tokens > max_bytes:
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
            return {"text": text, "audio_tokens": audio_tokens}
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
            try:
                audio_tokens = int(result.get("audio_tokens") or 0)
            except Exception:
                audio_tokens = 0
            if audio_tokens > 0:
                try:
                    g.db.query_database_insert(
                        "INSERT INTO usage_stats (prompt_tokens, completion_tokens, user_id, project, topic, api, model, purpose, service) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            audio_tokens,
                            0,
                            user_id,
                            project_id,
                            None,
                            "openai",
                            VoiceTranscriptionConfig.model(),
                            "audio_transcription",
                            "audio",
                        ),
                    )
                except Exception:
                    logger.exception("Failed to record audio usage for %s/%s", project_id, user_id)
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
    if not cfg.internal_api_key:
        return _json_error("Not enabled", 404)

    provided = (request.args.get("key") or "").strip()
    if not provided or not hmac.compare_digest(provided, cfg.internal_api_key):
        return _json_error("Unauthorized", 401)
    return None


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

def build_request_context(db) -> RequestContext:
    """Build the per-request context that used to be scattered across ``g.*``.

    Also sets ``g.*`` attrs for backward compatibility with admin/share
    blueprints and code that hasn't been migrated yet.
    """
    g.projectId = request.headers.get('projectId')
    g.uuid = request.headers.get('uuid')
    project_id = g.projectId
    user_id = g.uuid
    logger.debug('UUID received: "%s", type: %s', user_id, type(user_id))

    th = None
    base_topic = None
    current_topic = None
    response_count = 0
    topic_is_changing = False

    has_valid_user = user_id and user_id.strip() != ''

    if has_valid_user:
        logger.debug('Creating topic handler for valid UUID')
        th = topicHandler(db=db, project_id=project_id, user_id=user_id)
        base_topic = th.getCurrentTopic()
        g.th = th
        g.baseTopic = base_topic

        SessionInactivityCloser.close_stale_sessions(db, requires_db_fn=_requires_db)

        topics_log = th.getTopicsLog()
        response_count = topics_log[-1][5] if topics_log else 0

        if request.method == "POST" and request.is_json:
            request_data = request.get_json()
            if 'message' in request_data:
                response_count += 1
        g.response_count = response_count
        logger.debug('===Response Counter (before request):===: %s', response_count)

        logger.debug('===baseTopic ID (before request):===: %s', base_topic)
        topic_id, is_changing = th.switchTopic(response_count=response_count)
        current_topic = topic_id
        topic_is_changing = is_changing
        g.topic = current_topic
        if is_changing:
            g.topicIsChanging = True
        logger.debug('===Switch ID (before request):===: %s', current_topic)
    else:
        logger.debug('Skipping topic handler - no valid UUID')
        SessionInactivityCloser.close_stale_sessions(db, requires_db_fn=_requires_db)
        g.response_count = 0

    g.llm_purpose = "chat"
    g.llm_service = "core"

    return RequestContext(
        db=db,
        project_id=project_id,
        user_id=user_id,
        topic_handler=th,
        base_topic=base_topic,
        current_topic=current_topic,
        response_count=response_count,
        llm_purpose="chat",
        llm_service="core",
        topic_is_changing=topic_is_changing,
    )


@app.before_request
def _init_request_context():
    if not _requires_db():
        return

    if getattr(g, "db", None) is None:
        try:
            g.db = DB(cfg.db_config)
            g.db_error = None
        except Exception as e:
            g.db = None
            g.db_error = str(e)

    if getattr(g, "db", None) is None:
        return jsonify(error="Database unavailable", details=getattr(g, "db_error", None)), 503

    g.ctx = build_request_context(g.db)

@app.after_request
def updateCounter(response):
    if not _requires_db():
        return response
    ctx = getattr(g, 'ctx', None)
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        base = ctx.base_topic if ctx else getattr(g, 'baseTopic', None)
        g.th.updateResponseCounter(base_topic=base)
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

# Health endpoint (no DB required)
@app.route('/api/health', methods=['GET'])
def health():
    try:
        credentials.get_db_config()
        db_configured = True
        db_config_error = None
    except Exception as e:
        db_configured = False
        db_config_error = str(e)

    return jsonify(ok=True, version=cfg.app_version, db_required=_requires_db(), db_configured=db_configured, db_config_error=db_config_error), 200

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
        try:
            reply_input = ReplyInput.from_payload(payload, headers=dict(request.headers))
        except ValueError as ve:
            return jsonify(error=str(ve)), 400

        ctx = getattr(g, 'ctx', None)
        logger.debug('Processing reply for user: %s, project: %s', g.uuid, g.projectId)
        logger.debug('baseTopic: %s, topic: %s', getattr(g, 'baseTopic', None), getattr(g, 'topic', None))

        handler = ReplyHandler(g.th)
        analysis = AnalysisService(g.db, g.projectId)

        if not reply_input.wants_stream:
            result = handler.process(reply_input)
            if result.topic_status == "closed":
                analysis.maybe_analyze(g.uuid)
            return jsonify(result.to_dict(APP_VERSION))

        def sse(data: str) -> str:
            return f"data: {data}\n\n"

        def generate():
            final_result = None
            for event_type, event_data in handler.process_stream(reply_input):
                if event_type == "keepalive":
                    yield ":\n\n"
                elif event_type == "delta":
                    yield sse(json.dumps({"type": "delta", "delta": event_data}))
                elif event_type == "final":
                    final_result = event_data
                    yield sse(json.dumps(final_result.to_dict(APP_VERSION) | {"type": "final"}))

            if final_result and final_result.topic_status == "closed":
                analysis.maybe_analyze(g.uuid)

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
            topic_id, is_changing = g.th.switchTopic(response_count=g.response_count)
            g.topic = topic_id
            if is_changing:
                g.topicIsChanging = True
            progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
            response_text = chat.provideResponse(first_answer)
            status = chat.retrieveTopicStatus()
            answers = chat.retrieveDefinedAnswers()
            resp = dict(response=response_text, status=status, answers=answers, progress=progress, version=APP_VERSION)
            debug = _build_reply_debug(chat)
            if debug:
                resp["_debug"] = debug
            return jsonify(resp)
        response_text = chat.provideInitialResponse()
        status = chat.retrieveTopicStatus()
        answers = chat.retrieveDefinedAnswers()
        progress = g.th.getTopicProgress() if hasattr(g, "th") else {"current": 0, "total": 0, "ratio": 0}
        resp = dict(response=response_text, status=status, answers=answers, progress=progress, version=APP_VERSION)
        debug = _build_reply_debug(chat)
        if debug:
            resp["_debug"] = debug
        return jsonify(resp)
    except Exception as e:
        logger.exception('Error in initialize_interview: %s', str(e))
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

    openai_valid = False
    try:
        if cfg.openai_key:
            client = OpenAI(api_key=cfg.openai_key)
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
            "openai_key_set": bool(cfg.openai_key),
            "openai_key_valid": openai_valid,
            "azure_key_set": bool(cfg.azure_key),
            "panda_key_set": bool(cfg.openai_panda_key),
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


app.register_blueprint(admin_bp)
app.register_blueprint(share_bp)


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
    app.run(host='0.0.0.0', port=cfg.port, debug=False)
