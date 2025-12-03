import os
from flask import Flask, send_from_directory, request, jsonify, g
from flask_cors import CORS
import logging

# Import all your existing backend functionality
import openai
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from llmInterface import LLM
import uuid
import json
import credentials
from database import DB
from topic import topicHandler
from conversationInterface import conversation
import platform

if platform.system() == 'Linux':
    from heartbeat import heartbeat

# Create Flask app that serves both frontend and backend
app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
psycopg2.extras.register_uuid()

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
    db = getattr(g, 'db', None)
    if db is None:
        g.db = DB(credentials.db_config)

@app.before_request
def topirHandlerInstance():
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
def responseCounter():
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
def setglobalvars():
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        logger.debug('===baseTopic ID (beforere request):===: %s', g.baseTopic)
        g.topic = g.th.switchTopic()
        logger.debug('===Switch ID (beforere request):===: %s', g.topic)

@app.after_request
def updateCounter(response):
    if hasattr(g, 'th') and g.uuid and g.uuid.strip() != '':
        g.th.updateResponseCounter()
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
    if path.startswith('api/'):
        return  # Let API routes handle this
    if path and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

# Backend API routes (with /api prefix)
@app.route('/api/respondent/', methods=['POST'])
def create_respondent():
    project = request.headers.get('projectId')
    external_id = request.headers.get('externalId')
    check_if_project_exists()
    json = request.get_json()
    now = datetime.now(timezone.utc)
    generated_uuid = uuid.uuid4()
    query = "INSERT INTO respondents (id,created_at,project,email,consent,external_id) VALUES (%s,%s,%s,%s,%s,%s)"
    query_params = (generated_uuid,now,project,json['email'],json['consent'],external_id)
    g.db.query_database_insert(query,query_params)
    return jsonify(uuid=generated_uuid, projectId=project)

@app.route('/api/project/', methods=['GET'])
def get_project():
    project = request.headers.get('projectId')
    query = "SELECT name,logo,colour,welcome_title,welcome_message,success_title,success_message,welcome_second_title,welcome_second_message,consent,cta_next,cta_reply,cta_abort,cta_restart,question_title,answer_title,answer_placeholder,loading,collect_email,email_title,email_placeholder,consent_link,skip_welcome,dark_mode,inline_consent from projects where id=%s"
    query_params = (project,)
    project_data = g.db.query_database_one(query,query_params)
    if project_data:
        labels = [
        "name", "logo", "colour", "welcome_title", "welcome_message",
        "success_title", "success_message", "welcome_second_title",
        "welcome_second_message", "consent", "cta_next", "cta_reply",
        "cta_abort", "cta_restart", "question_title", "answer_title",
        "answer_placeholder", "loading", "collect_email", "email_title",
        "email_placeholder", "consent_link", "skip_welcome", "dark_mode", "inline_consent"
        ]
        project_dict = {label: value for label, value in zip(labels, project_data)}
        return jsonify([project_dict])
    else:
        return jsonify({"error": "Project not found"}), 404

@app.route('/api/reply/', methods=['POST'])
def gpt_response():
    try:
        check_if_user_exists()
        json = request.get_json()
        user_response = json['message']
        
        logger.debug('Processing reply for user: %s, project: %s', g.uuid, g.projectId)
        logger.debug('baseTopic: %s, topic: %s', getattr(g, 'baseTopic', None), getattr(g, 'topic', None))
        
        chat = conversation(g.th)
        response = chat.provideResponse(user_response)
        status = chat.retrieveTopicStatus()
        answers = chat.retrieveDefinedAnswers()
        
        return jsonify(response=response, status=status, answers=answers)
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
            g.topic = g.th.switchTopic()
            return jsonify(response=chat.provideResponse(first_answer), status=chat.retrieveTopicStatus(), answers=chat.retrieveDefinedAnswers())
        return jsonify(response=chat.provideInitialResponse(), status=chat.retrieveTopicStatus(), answers=chat.retrieveDefinedAnswers())
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
    key = request.args.get('key')
    if key == '3yTgJUQnPjs4L':
        heartbeat()
        return jsonify(status=True)

@app.route('/api/debug/', methods=['GET'])
def debug_info():
    key = request.args.get('key')
    if key == '3yTgJUQnPjs4L':
        import os
        return jsonify({
            'openai_key_set': bool(os.environ.get('OPENAI_API_KEY')),
            'azure_key_set': bool(os.environ.get('AZURE_OPENAI_KEY')),
            'panda_key_set': bool(os.environ.get('OPENAI_PANDA_KEY')),
            'db_config': 'configured'
        })
    return jsonify(error='Unauthorized'), 401

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
