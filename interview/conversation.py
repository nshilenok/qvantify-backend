"""Conversation handling for interview sessions.

Builds prompts, manages message history, orchestrates LLM calls for the
interview chat loop.
"""

from llmInterface import LLM
import logging
import re
import credentials
from . import topic_engine
from .topic_engine import strip_raw_tool_text

logger = logging.getLogger(__name__)


def _g_attr(name, default=None):
    """Read a Flask ``g`` attribute, returning *default* outside app context."""
    try:
        from flask import g, has_app_context
        if has_app_context():
            return getattr(g, name, default)
    except Exception:
        pass
    return default


class conversation():

		def __init__(self, topic_instance, db=None, project_id=None,
					 user_id=None, topic_id=None, base_topic=None):
			self.project = project_id if project_id is not None else _g_attr('projectId')
			self.uuid = user_id if user_id is not None else _g_attr('uuid')
			self.DB = db if db is not None else _g_attr('db')
			self.topic = topic_id if topic_id is not None else _g_attr('topic')
			self.base_topic = base_topic if base_topic is not None else _g_attr('baseTopic', self.topic)
			self.topic_instance = topic_instance

		@property
		def _current_topic(self):
			"""The current topic — prefers g.topic (updated by topic switches)
			during migration, falls back to self.topic."""
			gt = _g_attr('topic')
			return gt if gt is not None else self.topic

		@property
		def _base_topic(self):
			gt = _g_attr('baseTopic')
			return gt if gt is not None else self.base_topic

		def retrieveTopic(self):
			topic = self.topic_instance.findTopicById(self._current_topic)[2]
			return topic

		def retrieveTopicStatus(self):
			topic_status = self.topic_instance.findTopicLogEntry(self._current_topic)
			if topic_status:
				if topic_status[4] == 1:
					return "open"
				else:
					return "closed"
			else:
				return "open"

		def retrieveDefinedAnswers(self):
			query = "SELECT defined_answers FROM topics WHERE id=%s"
			query_params = (self._current_topic,)
			results = self.DB.query_database_one(query, query_params)[0]
			return results

		def retrieveRecords(self):
			query = "SELECT created_at,role,content,topic FROM records WHERE user_id=%s AND project=%s ORDER by created_at ASC"
			query_params = (self.uuid, self.project)
			results = self.DB.query_database_all(query, query_params)
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
			cur = self._current_topic
			base = self._base_topic
			for message in records:
				if message[1] == "system" and message[3] not in (cur, base):
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
			query_params = (self.project,)
			results = self.DB.query_database_one(query, query_params)[0]
			prompt = results or credentials.default_prompt
			return self._render_prompt_template(prompt, topic_id or self._current_topic)

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


		def _store(self, role, content, voice_input=False, audio_tokens=0):
			self.DB.store_message(self.project, self.uuid, self._base_topic,
								 self._current_topic, role, content,
								 voice_input, audio_tokens)

		def _is_topic_changing(self):
			return _g_attr('topicIsChanging') is not None

		def provideResponse(self, user_input=None):
			cur = self._current_topic
			promptType = self.topic_instance.getTopicType(cur)
			logger.debug('===Getting prompt type (%s) for topic: %s', promptType, cur)
			chatGPT = LLM(db=self.DB, project_id=self.project)

			if user_input is not None and self.retrieveTopicStatus() == "open":
				self._store("user", user_input)
			else:
				self._store("user", user_input)
				return None
			messages = self.buildModelMessages()
			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()

			topic_changing = self._is_topic_changing()

			if promptType == "prompt" and topic_changing:
				self._store("system", system_prompt)
				response = chatGPT.getResponse(messages)
				self._store("assistant", response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "prompt" and not topic_changing:
				response = chatGPT.getResponse(messages)
				logger.debug('===Generatint response===: %s', response)
				self._store("assistant", response.choices[0].message.content)
				return response.choices[0].message.content

			elif promptType == "auto" and topic_changing:
				self._store("system", system_prompt)
				response = chatGPT.getResponse(messages, topic_engine.TOOL_SPEC)
				content = response.choices[0].message.content or ""
				switched = topic_engine.handle_tool_call(response, topic_engine=self.topic_instance)
				if not switched and "interview_topic_over" in content:
					topic_engine.force_switch_from_text(self.topic_instance)
					switched = True
				if switched:
					logger.debug('===auto topic attempt 1: %s', self._current_topic)
					answer = self.provideInitialResponse()
					return answer
				self._store("assistant", content)
				return content

			elif promptType == "auto" and not topic_changing:
				response = chatGPT.getResponse(messages, topic_engine.TOOL_SPEC)
				content = response.choices[0].message.content or ""
				switched = topic_engine.handle_tool_call(response, topic_engine=self.topic_instance)
				if not switched and "interview_topic_over" in content:
					topic_engine.force_switch_from_text(self.topic_instance)
					switched = True
				if switched:
					logger.debug('===auto topic attempt 2: %s', self._current_topic)
					answer = self.provideInitialResponse()
					return answer
				logger.debug('===Generating response (auto/none)===: %s', response)
				self._store("assistant", content)
				return content

			elif promptType == "single_question" and topic_changing:
				self._store("assistant", self.retrieveTopic())
				return self.retrieveTopic()

			elif promptType == "single_question" and not topic_changing:
				history = self.retrieveConverasationHistory()
				if not history:
					self._store("assistant", self.retrieveTopic())
					return self.retrieveTopic()
				return history[-1]["content"]

		_TOPIC_SWITCH_INSTRUCTION = (
			"\n\n[TOPIC SWITCH] The previous conversation topic has ended. "
			"You MUST now ask the question from CURRENT TOPIC. "
			"Do NOT continue the previous topic's conversation."
		)

		def _buildInitialMessages(self):
			"""Build messages for provideInitialResponse.

			Uses the current topic's system prompt (with a topic-transition
			boundary appended) plus conversation history so the model asks
			the new topic's question instead of continuing the old conversation.
			"""
			records = self.retrieveRecords()
			system_prompt = (
				self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()
				+ self._TOPIC_SWITCH_INSTRUCTION
			)
			history = []
			for message in records:
				role = message[1]
				content = message[2]
				if role not in ("user", "assistant"):
					continue
				history.append({"role": role, "content": content})
			return [{"role": "system", "content": system_prompt}] + history

		def provideInitialResponse(self, _depth=0):
			cur = self._current_topic
			promptType = self.topic_instance.getTopicType(cur)
			chatGPT = LLM(db=self.DB, project_id=self.project)

			system_prompt = self.retrieveTopic() + '\n \n' + self.getDefaultPrompt()

			if promptType == "prompt" or promptType == "auto":
				logger.debug('Initial Response (prompt or auto): %s', self._is_topic_changing())
				self._store("system", system_prompt)
				history = self._buildInitialMessages()
				response = chatGPT.getResponse(history)
				msg = response.choices[0].message
				raw = msg.content or ""
				content = strip_raw_tool_text(raw)
				if not content and raw and _depth < 3:
					logger.warning(
						'Initial response was raw tool text for topic %s, forcing switch (depth=%d)',
						cur, _depth,
					)
					next_id = topic_engine.force_switch_from_text(self.topic_instance)
					if next_id:
						return self.provideInitialResponse(_depth=_depth + 1)
				self._store("assistant", content)
				return content

			elif promptType == "single_question":
				logger.debug('Initial Response (single question): %s', self._is_topic_changing())
				self._store("assistant", self.retrieveTopic())
				return self.retrieveTopic()

			else:
				logger.debug('===Retrieving history:===')
				history = self.retrieveConverasationHistory()
				if not history:
					if promptType in ("prompt", "auto"):
						history = [{"role": "system", "content": system_prompt}]
						self._store("system", system_prompt)
						response = chatGPT.getResponse(history)
						self._store("assistant", response.choices[0].message.content)
						return response.choices[0].message.content
					if promptType == "single_question":
						self._store("assistant", self.retrieveTopic())
						return self.retrieveTopic()
				return history[-1]["content"]
