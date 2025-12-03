import json
from llmInterface import LLM
from database import DB
import credentials
import app
import threading
from nltk import tokenize
import nltk
import sys
from label_prompt import labels

nltk.download('punkt')

db = DB(credentials.db_config)

def get_interview(uuid,project):
	records = db.get_records(uuid,project)
	print(f"Interview lenght: {len(records)}, uuid: {uuid}")
	if len(records) < 4:
		print("Skipping")
		return None
	history = ""
	roles = []
	content = []
	for message in records:
		roles.append(message[1])
		content.append(message[2])
	for role, cont in zip(roles, content):
		entry = f"{role}: {cont} \n\n"
		history = history+entry
	return history


def save_interview_analysis(summary,sentiment,title,uuid,facts):
	print(f"Title: {title} \nSentiment: {sentiment} \nSummary: {summary}\n uuid: {uuid}")
	query = "UPDATE interviews SET title=%s, sentiment=%s, summary=%s, facts=%s where respondent=%s"
	query_params = (title,sentiment,summary,facts,uuid)
	db.query_database_insert(query,query_params)
	print("Stored to DB successfully")

def save_label(label,insight_id):
	print(f"Label: {label}")
	query = "UPDATE interviews_sentences SET label=%s where id=%s"
	query_params = (label,insight_id)
	db.query_database_insert(query,query_params)
	print("Stored to DB successfully")


def analyze_interview(uuid,project):
	prompt = get_interview(uuid,project)
	if prompt is None:
		return None
	interview = []
	interview.insert(0,{"role": "system", "content": "You are an analyst of interviews. This analysis will be used to analyze many interviews conducted for the same reasearch. Your job is to perform qualitative analysis and provide specific answers, do not quote, only provide answers you are asked. Some interviews might be incomplete"})
	message_with_interview = f"Below is the interview. Tasks: 1.Provide a short summary - once sentence focusing on the main point of the interview. 2.Come up with a title. 3.Detect sentiment: negative, neutral or postiive. 4. Extract insights: Please extract key insights from the interview. Each insight should be a clear and concise statement that stands on its own, meaning it should inlcude full context without reference to other sentences. Focus only on significant points, conclusions, or facts that are evident from the interview. Present these insights in a bullet-point format, ensuring that each point captures a complete thought or piece of information valuable in isolation. For example, if the interviewee discusses the importance of innovation in technology, an insight might be: 'User says innovation is deemed crucial for staying ahead in the technology sector.' Note that 'system' entries contain instructions for the interviewer and must be considered.. \n \n The interview: \n {prompt} \n THE END \n"
	interview.append({"role": "user", "content": message_with_interview })
	functions = [
    {
    	"type": "function",
    	"function":{
	        "name": "interview_analysis",
	        "description": "Analyze the interview by providing sentiment analysis, summary, facts and title.",
	        "parameters": {
	            "type": "object",
	            "properties": {
	                "summary": {
	                    "type": "string",
	                    "description": "Explain the interview in one sentence"
	                },
	                "sentiment": {
	                    "type": "string",
	                    "description": "Sentiment of the interview: negative, neutral, positive"
	                }, 
	                "title": {
	                    "type": "string",
	                    "description": "A title for the interview",
	                },
	                "insights": {
	                		"type": "string",
	                		"description": "Paragraph of semicolon seperated insights from the interview."
	                		}
	            },
	            "required": ["summary","title","sentiment","insights"]
	        }
    }}
	]

	gpt = LLM(db)
	response = gpt.getResponseAzure(interview,functions)
	print(response)
	response_message = response.choices[0].message

	if response_message.tool_calls:
		available_functions = {"interview_analysis": save_interview_analysis,}
		function_name = response_message.tool_calls[0].function.name
		function_to_call = available_functions[function_name]
		function_args = json.loads(response_message.tool_calls[0].function.arguments)
		function_response = function_to_call(
            summary=function_args.get("summary"),
            sentiment=function_args.get("sentiment"),
            title=function_args.get("title"),
            uuid=uuid,
            facts=function_args.get("insights")
        )
		print(function_response)
		# exctractSentencesFromSummary(uuid,project,function_args.get("insights"))


def label_insight(insight_id,insight):
	print(insight)
	interview=[]
	interview.insert(0,{"role": "system", "content": f"Your job is to label a sentence according to the label names below. Provided sentence could only belong to one category/have one label. If no reasonable match can be made with the labels provided, label it 'other'. Call a function insight_labeler \n {labels}"})
	interview.append({"role": "user", "content": f"Label this insight from the interview: {insight}" })
	functions = [
    {
    	"type": "function",
    	"function":{
	        "name": "insight_labeler",
	        "description": "Analyze the input according to the categories/labels provided and apply a label.",
	        "parameters": {
	            "type": "object",
	            "properties": {
	                "label": {
	                    "type": "string",
	                    "description": "Label"
	                }
	            },
	            "required": ["label"]
	        }
    }}
	]

	gpt = LLM(db)
	response = gpt.getResponseAzure(interview,functions)
	print(response)
	response_message = response.choices[0].message

	if response_message.tool_calls:
		function_args = json.loads(response_message.tool_calls[0].function.arguments)
		function_response = save_label(
            label=function_args.get("label"),
            insight_id=insight_id
        )
		print(function_response)

def update_insights_labels(project_id):
	query = "SELECT id,sentence from interviews_sentences where label IS NULL and project=%s"
	query_params = (project_id,)
	sentences = db.query_database_all(query,query_params)
	for sentence in sentences:
		label_insight(sentence[0],sentence[1])

def update_interviews_with_analysis():
	query = "SELECT respondent,project from interviews where summary IS NULL"
	query_params = ("null",)
	interviews = db.query_database_all(query,query_params)
	for interview in interviews:
		analyze_interview(interview[0],interview[1])

# def updateInterviewsWithEmbeddings():
# 	query = "SELECT summary,id from interviews where summary_v IS NULL"
# 	query_params = ("null",)
# 	interviews = db.query_database_all(query,query_params)
# 	embedding = LLM(db)
# 	for interview in interviews:
# 		vector = embedding.getEmbedding(interview[0],'azure')
# 		query = "UPDATE interviews set summary_v=%s where id=%s"
# 		params = (vector,interview[1])
# 		db.query_database_insert(query, params)
# 		print(f"Vector inserted for interview {interview[1]}")
#
# def updateRecordsWithEmbeddings():
# 	if threading.current_thread().name == "t1":
# 		query = "SELECT content,id from records where mod(id,2)=0 AND role=\'user\' AND content_v IS NULL"
# 	else:
# 		query = "SELECT content,id from records where mod(id,2)>0 AND role=\'user\' AND content_v IS NULL"
#
# 	query_params = ("null",)
# 	interviews = db.query_database_all(query,query_params)
# 	embedding = LLM(db)
# 	for interview in interviews:
# 		vector = embedding.getEmbedding(interview[0],'azure')
# 		query = "UPDATE records set content_v=%s where id=%s"
# 		params = (vector,interview[1])
# 		db.query_database_insert(query, params)
# 		print(f"Vector inserted for {interview[1]}")
#
# def executeThreadedFunction(target):
# 	t1 = threading.Thread(target=target, name='t1')
# 	t2 = threading.Thread(target=target, name='t2')
#
# 	t1.start()
# 	t2.start()
# 	t1.join()
# 	t2.join()
#
# def exctractSentencesFromSummary(respondent,project,summary):
# 	#split_text = tokenize.sent_tokenize(summary)
# 	split_text = summary.split("; ")
# 	embedding = LLM(db)
# 	for sentence in split_text:
# 		vector = embedding.getEmbedding(sentence,'azure')
# 		query = "INSERT into interviews_sentences (respondent,project,sentence,sentence_v) VALUES (%s,%s,%s,%s)"
# 		params = (respondent,project,sentence,vector)
# 		db.query_database_insert(query,params)
#
# def retroUpdateInterviewSentences():
# 	query = "select respondent,id,project,summary from interviews where summary IS NOT NULL"
# 	params = ()
# 	interviews = db.query_database_all(query,params)
# 	for interview in interviews:
# 		exctractSentencesFromSummary(interview[0],interview[1],interview[2],interview[3])
#
# def embed_records():
# 	executeThreadedFunction(updateRecordsWithEmbeddings)

if __name__ == '__main__':
	#globals()[sys.argv[1]]()
	#update_insights_labels("fb12b01f-9fc3-4a27-b435-1c04694e1a52")
	update_interviews_with_analysis()
	#retroUpdateInterviewSentences()
	# executeThreadedFunction(updateRecordsWithEmbeddings)
	# updateInterviewsWithEmbeddings()
