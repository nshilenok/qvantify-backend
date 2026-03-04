from flask import g
from llmInterface import LLM
import logging
import re
import credentials
import autoTopic

logger = logging.getLogger(__name__)

_RAW_TOOL_CALL_RE = re.compile(r'interview_topic_over\s*\(\s*\{[^}]*\}\s*\)\s*', re.IGNORECASE)

def _strip_raw_tool_text(text: str) -> str:
	"""Remove raw interview_topic_over(...) text that the model sometimes emits as content."""
	if not text:
		return text
	return _RAW_TOOL_CALL_RE.sub("", text).strip()

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

		def _get_topic_meta(self, topic_id):
			if not topic_id:
				return None
			query = 'SELECT id, title, system, "group", sequence FROM topics WHERE id=%s'
			query_params = (topic_id,)
			row = self.DB.query_database_one(query, query_params)
			if not row:
				return None
			return {
				"id": row[0],
				"title": row[1],
				"system": row[2],
				"group": row[3],
				"sequence": row[4],
			}

		def _get_remaining_groups(self, current_sequence):
			if current_sequence is None:
				return []
			query = 'SELECT "group" FROM topics WHERE project=%s AND sequence > %s ORDER BY sequence ASC'
			query_params = (self.project, current_sequence)
			rows = self.DB.query_database_all(query, query_params)
			seen = set()
			remaining = []
			for row in rows:
				group = (row[0] or "").strip()
				if not group or group in seen:
					continue
				seen.add(group)
				remaining.append(group)
			return remaining

		def _build_prompt_context(self, topic_id):
			meta = self._get_topic_meta(topic_id)
			if not meta:
				return {}
			remaining_groups = self._get_remaining_groups(meta.get("sequence"))
			return {
				"group": meta.get("group") or "",
				"title": meta.get("title") or "",
				"system": meta.get("system") or "",
				"groups.remaining": ", ".join(remaining_groups),
			}

		def _render_prompt_template(self, template, topic_id):
			if not template:
				return template
			context = self._build_prompt_context(topic_id)
			if not context:
				return template

			def replace(match):
				key = match.group(1).strip()
				if key in context:
					return str(context[key])
				return match.group(0)

			return re.sub(r"\(\(([A-Za-z0-9_.-]+)\)\)", replace, template)

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
					content.append(message[2] + '\n \n' + self.getDefaultPrompt(message[3]))
				else:
					content.append(message[2])
			for role, cont in zip(roles, content):
				entry = {"role": role, "content": cont}
				history.append(entry)
			return history

		def getDefaultPrompt(self, topic_id=None):
			query = "SELECT default_prompt FROM projects WHERE id=%s"
			query_params = (g.projectId,)
			results = self.DB.query_database_one(query,query_params)[0]
			prompt = results or credentials.default_prompt
			return self._render_prompt_template(prompt, topic_id or g.topic)

		def buildModelMessages(self):
			records = self.retrieveRecords()
			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()
			history = []
			for message in records:
				role = message[1]
				content = message[2]
				if role not in ("user", "assistant"):
					continue
				history.append({"role": role, "content": content})
			return [{"role": "system", "content": system_prompt}] + history


		def provideResponse(self,user_input=None):
			promptType = self.topic_instance.getTopicType(g.topic)
			logger.debug('===Getting prompt type (%s) for topic: %s', promptType, g.topic)
			chatGPT = LLM()

			if user_input is not None and self.retrieveTopicStatus() == "open":
				g.db.store_message("user", user_input)
			else:
				g.db.store_message("user", user_input)
				return None
			messages = self.buildModelMessages()
			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()


			if promptType == "prompt" and getattr(g, 'topicIsChanging', None) is not None:
				self.DB.store_message("system",system_prompt)
				response = chatGPT.getResponse(messages)
				self.DB.store_message("assistant",response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "prompt" and getattr(g, 'topicIsChanging', None) is None:
				response = chatGPT.getResponse(messages)
				logger.debug('===Generatint response===: %s', response)
				self.DB.store_message("assistant", response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "auto" and getattr(g, 'topicIsChanging', None) is not None:
				self.DB.store_message("system",system_prompt)
				response = chatGPT.getResponse(messages, autoTopic.function)
				content = response.choices[0].message.content or ""
				if autoTopic.switchTopic(response) or "interview_topic_over" in content:
					if not autoTopic.switchTopic(response) and "interview_topic_over" in content:
						autoTopic.forceSwitchFromText(g.th)
					logger.debug('===auto topic attempt 1: %s', g.topic)
					answer = self.provideInitialResponse()
					return answer
				self.DB.store_message("assistant", content)
				return content

			elif promptType == "auto" and getattr(g, 'topicIsChanging', None) is None:
				response = chatGPT.getResponse(messages, autoTopic.function)
				content = response.choices[0].message.content or ""
				if autoTopic.switchTopic(response) or "interview_topic_over" in content:
					if not autoTopic.switchTopic(response) and "interview_topic_over" in content:
						autoTopic.forceSwitchFromText(g.th)
					logger.debug('===auto topic attempt 2: %s', g.topic)
					answer = self.provideInitialResponse()
					return answer
				logger.debug('===Generating response (auto/none)===: %s', response)
				self.DB.store_message("assistant", content)
				return content

			elif promptType == "single_question" and getattr(g, 'topicIsChanging', None) is not None:
				self.DB.store_message("assistant", self.retrieveTopic())
				return self.retrieveTopic()

			elif promptType == "single_question" and getattr(g, 'topicIsChanging', None) is None:
				history = self.retrieveConverasationHistory()
				if not history:
					self.DB.store_message("assistant", self.retrieveTopic())
					return self.retrieveTopic()
				return history[-1]["content"]

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
			
			if promptType == "prompt" or promptType == "auto":
				logger.debug('Initial Response (prompt or auto): %s', getattr(g, 'topicIsChanging', None))
				self.DB.store_message("system", system_prompt)
				history = self.buildModelMessages()
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
				msg = response.choices[0].message
				content = _strip_raw_tool_text(msg.content or "")
				self.DB.store_message("assistant", content)
				return content

			elif promptType == "single_question":
				logger.debug('Initial Response (single question): %s', getattr(g, 'topicIsChanging', None))
				self.DB.store_message("assistant", self.retrieveTopic())
				return self.retrieveTopic()

			else:
				logger.debug('===Retrieving history:===')
				history = self.retrieveConverasationHistory()
				if not history:
					if promptType in ("prompt", "auto"):
						history = [{"role": "system", "content": system_prompt}]
						self.DB.store_message("system", system_prompt)
						response = chatGPT.getResponse(history)
						self.DB.store_message("assistant", response.choices[0].message.content)
						return response.choices[0].message.content
					if promptType == "single_question":
						self.DB.store_message("assistant", self.retrieveTopic())
						return self.retrieveTopic()
				return history[-1]["content"]


