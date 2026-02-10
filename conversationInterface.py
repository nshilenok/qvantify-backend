from flask import g
from llmInterface import LLM
import logging
import credentials
import autoTopic

logger = logging.getLogger(__name__)

class conversation():

		def __init__(self,topic_instance):
			self.project =  g.projectId
			self.uuid =  g.uuid
			self.DB = g.db
			self.topic = g.topic
			self.topic_instance = topic_instance

		def retrieveTopic(self):
			topic = self.topic_instance.findTopicById(g.topic)[2]
			return topic
		
		def retrieveTopicStatus(self):
			topic_status = self.topic_instance.findTopicLogEntry(g.topic)
			if topic_status:
				if topic_status[4] == 1:
					return "open"
				else:
					return "closed"
			else:
				return "open"

		def retrieveDefinedAnswers(self):
			query = "SELECT defined_answers FROM topics WHERE id=%s"
			query_params = (g.topic,)
			results = self.DB.query_database_one(query,query_params)[0]
			return results

		def retrieveRecords(self):
			query = "SELECT created_at,role,content,topic FROM records WHERE user_id=%s AND project=%s ORDER by created_at ASC"
			query_params = (g.uuid,self.project)
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

		def retrieveConverasationHistory(self):
			records = self.retrieveRecords()
			history = []
			roles = []
			content = []
			for message in records:
				if message[1] == "system" and message[3] not in (g.topic, g.baseTopic):
					continue
				roles.append(message[1])
				if message[1] == "system":
					content.append(message[2] + '\n \n' + self.getDefaultPrompt())
				else:
					content.append(message[2])
			for role, cont in zip(roles, content):
				entry = {"role": role, "content": cont}
				history.append(entry)
			return history

		def getDefaultPrompt(self):
			query = "SELECT default_prompt FROM projects WHERE id=%s"
			query_params = (g.projectId,)
			results = self.DB.query_database_one(query,query_params)[0]
			if results:
				return results
			else:
				return credentials.default_prompt


		def provideResponse(self,user_input=None):
			promptType = self.topic_instance.getTopicType(g.topic)
			logger.debug('===Getting prompt type (%s) for topic: %s', promptType, g.topic)
			chatGPT = LLM()

			if user_input is not None and self.retrieveTopicStatus() == "open":
				g.db.store_message("user", user_input)
			else:
				g.db.store_message("user", user_input)
				return None
			history = self.retrieveConverasationHistory()
			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()


			if promptType == "prompt" and getattr(g, 'topicIsChanging', None) is not None:

				history.append({"role": "system", "content": system_prompt})
				self.DB.store_message("system",system_prompt)
				response = chatGPT.getResponse(history)
				self.DB.store_message("assistant",response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "prompt" and getattr(g, 'topicIsChanging', None) is None:
				response = chatGPT.getResponse(history)
				logger.debug('===Generatint response===: %s', response)
				self.DB.store_message("assistant", response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "auto" and getattr(g, 'topicIsChanging', None) is not None:
				history.append({"role": "system", "content": system_prompt})
				self.DB.store_message("system",system_prompt)
				response = chatGPT.getResponse(history, autoTopic.function)
				if autoTopic.switchTopic(response):
					logger.debug('===auto topic attempt 1: %s', g.topic)
					answer = self.provideInitialResponse()
					return answer
				self.DB.store_message("assistant",response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "auto" and getattr(g, 'topicIsChanging', None) is None:
				response = chatGPT.getResponse(history, autoTopic.function)
				if autoTopic.switchTopic(response):
					logger.debug('===auto topic attempt 2: %s', g.topic)
					answer = self.provideInitialResponse()
					return answer
				logger.debug('===Generating response (auto/none)===: %s', response)
				self.DB.store_message("assistant", response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "single_question" and getattr(g, 'topicIsChanging', None) is not None:
				self.DB.store_message("assistant", self.retrieveTopic())
				return self.retrieveTopic()

			elif promptType == "single_question" and getattr(g, 'topicIsChanging', None) is None:
				return self.retrieveConverasationHistory()[-1]['content']

		def provideInitialResponse(self):
			promptType = self.topic_instance.getTopicType(g.topic)
			chatGPT = LLM()

			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()

			# region agent log
			try:
				import json as _json
				from datetime import datetime as _dt
				payload = {
					"sessionId": "debug-session",
					"runId": "run1",
					"hypothesisId": "H3",
					"location": "conversationInterface.py:provideInitialResponse",
					"message": "provideInitialResponse entry",
					"data": {
						"promptType": promptType,
						"topicIsChanging": bool(getattr(g, 'topicIsChanging', None) is not None),
						"system_len": len(system_prompt or ""),
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
			# endregion agent log
			
			if getattr(g, 'topicIsChanging', None) is not None:

				if promptType == "prompt" or promptType == "auto":
					logger.debug('Initial Response (prompt or auto): %s', getattr(g, 'topicIsChanging', None))
					history = []
					self.DB.store_message("system", system_prompt)
					history.append({"role": "system", "content": system_prompt})
					# region agent log
					try:
						import json as _json
						from datetime import datetime as _dt
						payload = {
							"sessionId": "debug-session",
							"runId": "run1",
							"hypothesisId": "H3",
							"location": "conversationInterface.py:provideInitialResponse",
							"message": "calling LLM for initial response",
							"data": {"history_len": len(history)},
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
					# endregion agent log
					response = chatGPT.getResponse(history)
					self.DB.store_message("assistant",response.choices[0].message.content)
					# region agent log
					try:
						import json as _json
						from datetime import datetime as _dt
						payload = {
							"sessionId": "debug-session",
							"runId": "run1",
							"hypothesisId": "H3",
							"location": "conversationInterface.py:provideInitialResponse",
							"message": "LLM responded",
							"data": {"response_len": len(response.choices[0].message.content or "")},
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
					# endregion agent log
					return response.choices[0].message.content

				elif promptType == "single_question":
					logger.debug('Initial Response (single question): %s', getattr(g, 'topicIsChanging', None))
					self.DB.store_message("assistant", self.retrieveTopic())
					return self.retrieveTopic()

			else:
				logger.debug('===Retrieving history:===')
				return self.retrieveConverasationHistory()[-1]['content']





