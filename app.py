import openai
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, g
from datetime import datetime, timezone, timedelta
from llmInterface import LLM
import uuid
import json
import credentials
from database import DB
import logging
from topic import topicHandler
from conversationInterface import conversation
import platform

if platform.system() == 'Linux':
    from heartbeat import heartbeat


logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
psycopg2.extras.register_uuid()

def check_if_user_exists():
	#todo: Try Except, throw an exception when user does not exist and get rid of the IF chain
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


app = Flask(__name__)

@app.before_request
def get_db():
    db = getattr(g, 'db', None)
    if db is None:
       	g.db = DB(credentials.db_config)


@app.before_request
def topirHandlerInstance():
	g.projectId = request.headers.get('projectId')
	g.uuid = request.headers.get('uuid')
	if getattr(g, "uuid", None) is not None:
		g.th = topicHandler() 
		g.baseTopic = g.th.getCurrentTopic()



@app.before_request
def responseCounter():
	if getattr(g, "uuid", None) is not None:
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

@app.before_request
def setglobalvars():
	if getattr(g, "uuid", None) is not None:
		logger.debug('===baseTopic ID (beforere request):===: %s', g.baseTopic)
		g.topic = g.th.switchTopic()
		logger.debug('===Switch ID (beforere request):===: %s', g.topic)

@app.after_request
def updateCounter(response):
	user_uuid = getattr(g, 'uuid', None)
	if user_uuid is not None:
		g.th.updateResponseCounter()
		return response
	return response


@app.teardown_appcontext
def close_connection(exception):
	db = getattr(g, 'db', None)
	if db is not None:
		g.db.close()

@app.route('/api/reply/', methods=['POST'])
def gpt_response():
	check_if_user_exists()
	json = request.get_json()
	user_response = json['message']
	
	chat = conversation(g.th)

	return jsonify(response=chat.provideResponse(user_response), status=chat.retrieveTopicStatus(), answers=chat.retrieveDefinedAnswers())

@app.route('/api/interview/', methods=['GET'])
def initialize_interview():
	check_if_user_exists()
	first_answer = request.args.get('first_answer')
	chat = conversation(g.th)
	if first_answer and getattr(g, 'topicIsChanging', None) is not None:
		logger.info('First answer was provided in GET parameters: %s, for user: %s', first_answer, g.uuid)
		chat.provideInitialResponse()
		g.response_count = 1
		g.baseTopic = g.th.getCurrentTopic()
		g.topic = g.th.switchTopic()
		return jsonify(response=chat.provideResponse(first_answer), status=chat.retrieveTopicStatus(), answers=chat.retrieveDefinedAnswers())
	return jsonify(response=chat.provideInitialResponse(), status=chat.retrieveTopicStatus(), answers=chat.retrieveDefinedAnswers())

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


@app.route('/api/quote/', methods=['GET'])
def findClose():
	# text = request.args.get('text')
	# project = text = request.args.get('projectid')
	# embedding = LLM()
	# vector = embedding.getEmbedding(text,'azure')
	# query = "SELECT id,content,1-(content_v <=> %s::vector) as similarity from records where role=\'user\' AND content_v IS NOT NULL and project=%s ORDER by similarity DESC LIMIT 10"
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
def debug_endpoint():
	try:
		project = request.headers.get('projectId')
		user_uuid = request.headers.get('uuid')
		
		# Check if user exists
		if user_uuid:
			user_query = "SELECT id,project FROM respondents WHERE id=%s"
			user_result = g.db.query_database_one(user_query, (user_uuid,))
			user_exists = user_result is not None
		else:
			user_exists = False
			user_result = None
		
		# Check topics for project
		topic_query = "SELECT COUNT(*) FROM topics WHERE project=%s"
		topic_result = g.db.query_database_one(topic_query, (project,))
		topic_count = topic_result[0] if topic_result else 0
		
		# Get first topic if exists
		first_topic_query = "SELECT id, system, topic_type FROM topics WHERE project=%s ORDER BY sequence ASC LIMIT 1"
		first_topic = g.db.query_database_one(first_topic_query, (project,))
		
		return jsonify(
			success=True, 
			projectId=project, 
			uuid=user_uuid,
			userExists=user_exists,
			userDbResult=str(user_result) if user_result else None,
			topicCount=topic_count,
			firstTopic=str(first_topic) if first_topic else None,
			message="Debug info"
		)
	except Exception as e:
		return jsonify(success=False, error=str(e)), 500



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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=105)