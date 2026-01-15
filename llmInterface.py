import credentials
import openai
from openai import AzureOpenAI
from openai import OpenAI
from flask import g, has_request_context
import os
import logging
from typing import Generator, Optional, Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

class LLM():
	"""docstring for LLM"""
	def __init__(self,db=None):
		if g:
			self.project =  g.projectId
		else:
			self.project = None

		if self.project == credentials.panda_project:
			self.key = credentials.openaiapi_panda_key
		else:
			self.key = credentials.openaiapi_key

		if db: #setting stuff here when app is working out of context and DB connection is shared
			self.DB = db
		else:
			self.DB = g.db
		self.config = self.getConfig()
		self.api = self.getApi()

	def getConfig(self):
		query_params = (self.project,)
		response = None
		max_token_value = None
		try:
			query = "select model,temperature,max_tokens,top_p,api from projects where id=%s"
			response = self.DB.query_database_one(query,query_params)
			if response:
				max_token_value = response[2]
		except Exception as e:
			logger.warning("Project config missing max_tokens; falling back to max_completion_tokens: %s", str(e))
			query = "select model,temperature,max_completion_tokens,top_p,api from projects where id=%s"
			response = self.DB.query_database_one(query,query_params)
			if response:
				max_token_value = response[2]
		default_values = {
		'model': 'gpt-5.2',
		'temperature': 1,
		'max_tokens': 256,
		'top_p': 1
		}
		analysis_values = {
		'model': 'gpt-5.2',
		'temperature': 1,
		'max_tokens': 512,
		'top_p': 1
		}
		if response:
			config = {
			'model': response[0] if response[0] is not None else default_values['model'],
			'temperature': response[1] if response[1] is not None else default_values['temperature'],
			'max_tokens': max_token_value if max_token_value is not None else default_values['max_tokens'],
			'top_p': response[3] if response[3] is not None else default_values['top_p']
			}
			return config
		else:
			return analysis_values

	def getApi(self):
		query = "select api from projects where id=%s"
		query_params = (self.project,)
		response = self.DB.query_database_one(query,query_params)
		if response:
			api = response[0]
		else:
			api = "openai"
		return api

	def getResponseAzure(self,messages,tools=None,tool_choice=None):
		config = self.config
		os.environ["AZURE_OPENAI_API_KEY"] = credentials.azureopenai_key
		client = AzureOpenAI(api_version="2023-09-01-preview",azure_endpoint="https://qvantify-se.openai.azure.com")
		if tools:
			if tool_choice:
				response = client.chat.completions.create(**config,messages=messages,tools=tools,tool_choice=tool_choice)
			else:
				response = client.chat.completions.create(**config,messages=messages,tools=tools)
		else:
			response = client.chat.completions.create(**config,messages=messages)
		logger.debug('==========================Azure Output===========================: %s', response)
		self.saveUsage(response)
		client.close()
		return response


	def getResponseOpenAI(self,messages,tools=None,tool_choice=None):
		config = dict(self.config)
		# OpenAI gpt-5.* models require max_completion_tokens instead of max_tokens.
		if str(config.get("model", "")).startswith("gpt-5"):
			if "max_tokens" in config:
				config["max_completion_tokens"] = config.pop("max_tokens")
		os.environ["OPENAI_API_KEY"] = self.key
		client = OpenAI() 
		# region agent log
		try:
			import json as _json
			from datetime import datetime as _dt
			payload = {
				"sessionId": "debug-session",
				"runId": "run1",
				"hypothesisId": "H3",
				"location": "llmInterface.py:getResponseOpenAI",
				"message": "OpenAI request start",
				"data": {"model": str(config.get("model", "")), "has_tools": bool(tools)},
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
		if tools:
			if tool_choice:
				response = client.chat.completions.create(**config,messages=messages,tools=tools,tool_choice=tool_choice)
			else:
				response = client.chat.completions.create(**config,messages=messages,tools=tools)
		else:
			response = client.chat.completions.create(**config,messages=messages)
		# region agent log
		try:
			import json as _json
			from datetime import datetime as _dt
			payload = {
				"sessionId": "debug-session",
				"runId": "run1",
				"hypothesisId": "H3",
				"location": "llmInterface.py:getResponseOpenAI",
				"message": "OpenAI request done",
				"data": {"has_response": response is not None},
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
		logger.debug('==========================OpenAI Output===========================: %s', response)
		self.saveUsage(response)
		client.close()
		return response

	def streamResponseOpenAI(self, messages, tools=None) -> Generator[Tuple[str, Any], None, None]:
		"""
		Stream OpenAI chat.completions and yield:
		- ("delta", str) for content token deltas
		- ("tool_call", dict) for tool call deltas (best-effort passthrough)
		- ("done", None) at end
		"""
		config = dict(self.config)
		# OpenAI gpt-5.* models require max_completion_tokens instead of max_tokens.
		if str(config.get("model", "")).startswith("gpt-5"):
			if "max_tokens" in config:
				config["max_completion_tokens"] = config.pop("max_tokens")
		os.environ["OPENAI_API_KEY"] = self.key
		client = OpenAI()
		try:
			if tools:
				stream = client.chat.completions.create(**config, messages=messages, tools=tools, stream=True)
			else:
				stream = client.chat.completions.create(**config, messages=messages, stream=True)
			for chunk in stream:
				if not getattr(chunk, "choices", None):
					continue
				choice = chunk.choices[0]
				delta = getattr(choice, "delta", None)
				if delta is None:
					continue
				content = getattr(delta, "content", None)
				if content:
					yield ("delta", content)
				tool_calls = getattr(delta, "tool_calls", None)
				if tool_calls:
					# tool_calls is a list of deltas; forward raw dict-ish representation
					for tc in tool_calls:
						yield ("tool_call", getattr(tc, "model_dump", lambda: tc)())
			yield ("done", None)
		finally:
			client.close()

	def getResponse(self,messages,tools=None,tool_choice=None):
		logger.info('USER %s SENDING THIS TO GPT: %s', getattr(g, "uuid", None), messages)
		try:
			if self.api == "openai":
				return self.getResponseOpenAI(messages,tools,tool_choice)
			if self.api == "azure":
				return self.getResponseAzure(messages,tools,tool_choice)
		except Exception as e:
			logger.exception('Error in LLM getResponse: %s', str(e))
			raise


	def getEmbedding(self,text,api):
		if api == "openai":
			raise Exception("Sorry, no OpenAI support for embeddings yet")
		if api == "azure":
			return self.getEmbeddingAzure(text)

	def getEmbeddingAzure(self, text):
		os.environ["AZURE_OPENAI_API_KEY"] = credentials.azureopenai_key
		client = AzureOpenAI(api_version="2023-09-01-preview",azure_endpoint="https://qvantify-se.openai.azure.com")
		response = client.embeddings.create(input=text, model="text-embedding-ada-002")
		return response.data[0].embedding

	def saveUsage(self, response):
		prompt_tokens = response.usage.prompt_tokens
		completion_tokens = response.usage.completion_tokens
		model = self.config['model']
		api = self.api
		if has_request_context():
			user_id = getattr(g, "uuid", None)
			project_id = getattr(g, "projectId", None) or self.project
			topic = getattr(g, "baseTopic", None)
			purpose = getattr(g, "llm_purpose", "chat")
			service = getattr(g, "llm_service", "core")
		else:
			user_id = None
			project_id = self.project
			topic = None
			purpose = "analysis"
			service = "batch"

		query = "INSERT INTO usage_stats (prompt_tokens, completion_tokens, user_id, project, topic, api, model, purpose, service) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
		params = (
			prompt_tokens,
			completion_tokens,
			user_id,
			project_id,
			topic,
			api,
			model,
			purpose,
			service,
		)
		try:
			self.DB.query_database_insert(query, params)
		except Exception:
			# Usage tracking must never break primary functionality.
			logger.exception("Failed to record usage_stats")



	