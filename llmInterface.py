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
	def __init__(self, db=None, project_id=None):
		if project_id is not None:
			self.project = project_id
		elif has_request_context() and hasattr(g, 'projectId'):
			self.project = g.projectId
		else:
			self.project = None

		if self.project == credentials.panda_project:
			self.key = credentials.openaiapi_panda_key
		else:
			self.key = credentials.openaiapi_key

		if db is not None:
			self.DB = db
		elif has_request_context() and hasattr(g, 'db'):
			self.DB = g.db
		else:
			self.DB = None
		self.config = self.getConfig()
		self.api = self.getApi()

	def getConfig(self):
		query_params = (self.project,)
		response = None
		max_token_value = None
		has_reasoning_effort = False
		try:
			query = "select model,temperature,max_tokens,top_p,api,reasoning_effort from projects where id=%s"
			response = self.DB.query_database_one(query,query_params)
			has_reasoning_effort = True
			if response:
				max_token_value = response[2]
		except Exception as e:
			logger.warning("Project config missing max_tokens; falling back to max_completion_tokens: %s", str(e))
			try:
				query = "select model,temperature,max_completion_tokens,top_p,api,reasoning_effort from projects where id=%s"
				response = self.DB.query_database_one(query,query_params)
				has_reasoning_effort = True
				if response:
					max_token_value = response[2]
			except Exception as e:
				logger.warning("Project config missing reasoning_effort; falling back to legacy columns: %s", str(e))
				try:
					query = "select model,temperature,max_tokens,top_p,api from projects where id=%s"
					response = self.DB.query_database_one(query,query_params)
					has_reasoning_effort = False
					if response:
						max_token_value = response[2]
				except Exception as e:
					logger.warning("Project config missing max_tokens; falling back to max_completion_tokens without reasoning_effort: %s", str(e))
					query = "select model,temperature,max_completion_tokens,top_p,api from projects where id=%s"
					response = self.DB.query_database_one(query,query_params)
					has_reasoning_effort = False
					if response:
						max_token_value = response[2]
		default_values = {
		'model': 'gpt-5.2',
		'temperature': 1,
		'top_p': 1,
		'reasoning_effort': 'low'
		}
		if response:
			reasoning_effort = response[5] if has_reasoning_effort and len(response) > 5 else None
			config = {
			'model': response[0] if response[0] is not None else default_values['model'],
			'temperature': response[1] if response[1] is not None else default_values['temperature'],
			'top_p': response[3] if response[3] is not None else default_values['top_p'],
			'reasoning_effort': reasoning_effort if reasoning_effort is not None else default_values['reasoning_effort']
			}
			if max_token_value is not None:
				config['max_tokens'] = max_token_value
			return config
		else:
			return default_values

	def getApi(self):
		query = "select api from projects where id=%s"
		query_params = (self.project,)
		response = self.DB.query_database_one(query,query_params)
		if response:
			api = response[0]
		else:
			api = "openai"
		return api

	def _prepare_openai_chat_config(self):
		config = dict(self.config)
		model_name = str(config.get("model", ""))

		if not model_name.startswith("gpt-4.1"):
			config.pop("temperature", None)
			config.pop("top_p", None)

		is_reasoning = (
			model_name.startswith("gpt-5")
			or model_name.startswith("o1")
			or model_name.startswith("o3")
			or model_name.startswith("o4")
		)
		if is_reasoning:
			if "max_tokens" in config:
				config["max_completion_tokens"] = config.pop("max_tokens")
			reasoning_effort = str(config.get("reasoning_effort", "") or "").strip()
			config["reasoning_effort"] = reasoning_effort or "low"
		else:
			config.pop("reasoning_effort", None)
		return config

	def _prepare_openai_messages(self, messages, config):
		model_name = str(config.get("model", "") or "")
		is_reasoning = (
			model_name.startswith("gpt-5")
			or model_name.startswith("o1")
			or model_name.startswith("o3")
			or model_name.startswith("o4")
		)
		if not is_reasoning:
			return messages
		prepared_messages = []
		for idx, message in enumerate(messages or []):
			if idx == 0 and isinstance(message, dict) and message.get("role") == "system":
				updated_message = dict(message)
				updated_message["role"] = "developer"
				prepared_messages.append(updated_message)
			else:
				prepared_messages.append(message)
		return prepared_messages

	def _prepare_azure_chat_config(self):
		config = dict(self.config)
		config.pop("reasoning_effort", None)
		return config

	def getResponseAzure(self,messages,tools=None,tool_choice=None):
		config = self._prepare_azure_chat_config()
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
		config = self._prepare_openai_chat_config()
		prepared_messages = self._prepare_openai_messages(messages, config)
		os.environ["OPENAI_API_KEY"] = self.key
		client = OpenAI() 
		if tools:
			if tool_choice:
				response = client.chat.completions.create(**config,messages=prepared_messages,tools=tools,tool_choice=tool_choice)
			else:
				response = client.chat.completions.create(**config,messages=prepared_messages,tools=tools)
		else:
			response = client.chat.completions.create(**config,messages=prepared_messages)
		logger.debug('==========================OpenAI Output===========================: %s', response)
		self.saveUsage(response)
		client.close()
		return response

	def _prepare_openrouter_chat_config(self):
		"""Build config dict for OpenRouter calls.

		OpenRouter passes params through to the upstream provider, so we
		keep temperature/top_p (most providers accept them) and handle
		reasoning via extra_body instead of the OpenAI-specific
		``reasoning_effort`` parameter.
		"""
		config = dict(self.config)
		model_name = str(config.get("model", ""))

		reasoning_effort = str(config.pop("reasoning_effort", "") or "").strip()

		is_openai_reasoning = (
			model_name.startswith("openai/gpt-5")
			or model_name.startswith("openai/o1")
			or model_name.startswith("openai/o3")
			or model_name.startswith("openai/o4")
		)
		extra_body = {}
		if is_openai_reasoning:
			config.pop("temperature", None)
			config.pop("top_p", None)
			if "max_tokens" in config:
				config["max_completion_tokens"] = config.pop("max_tokens")
			config["reasoning_effort"] = reasoning_effort or "low"
		elif "grok" in model_name.lower():
			if reasoning_effort:
				extra_body["reasoning"] = {"effort": reasoning_effort}
		return config, extra_body

	def _openrouter_client(self):
		return OpenAI(
			base_url="https://openrouter.ai/api/v1",
			api_key=credentials.openrouter_key,
		)

	_OPENROUTER_HEADERS = {
		"HTTP-Referer": "https://qvantify.app",
		"X-OpenRouter-Title": "Qvantify",
	}

	def getResponseOpenRouter(self, messages, tools=None, tool_choice=None):
		config, extra_body = self._prepare_openrouter_chat_config()
		prepared_messages = self._prepare_openai_messages(messages, config)
		client = self._openrouter_client()
		kwargs = dict(
			**config,
			messages=prepared_messages,
			extra_headers=self._OPENROUTER_HEADERS,
		)
		if extra_body:
			kwargs["extra_body"] = extra_body
		if tools:
			kwargs["tools"] = tools
			if tool_choice:
				kwargs["tool_choice"] = tool_choice
		response = client.chat.completions.create(**kwargs)
		logger.debug('==========================OpenRouter Output===========================: %s', response)
		self.saveUsage(response)
		client.close()
		return response

	def streamResponseOpenAI(self, messages, tools=None) -> Generator[Tuple[str, Any], None, None]:
		config = self._prepare_openai_chat_config()
		prepared_messages = self._prepare_openai_messages(messages, config)
		os.environ["OPENAI_API_KEY"] = self.key
		client = OpenAI()
		try:
			yield from self._stream_with_client(client, config, prepared_messages, tools)
		finally:
			client.close()

	def streamResponseOpenRouter(self, messages, tools=None) -> Generator[Tuple[str, Any], None, None]:
		config, extra_body = self._prepare_openrouter_chat_config()
		prepared_messages = self._prepare_openai_messages(messages, config)
		client = self._openrouter_client()
		try:
			yield from self._stream_with_client(
				client, config, prepared_messages, tools,
				extra_headers=self._OPENROUTER_HEADERS,
				extra_body=extra_body or None,
			)
		finally:
			client.close()

	def _stream_with_client(self, client, config, messages, tools=None, extra_headers=None, extra_body=None) -> Generator[Tuple[str, Any], None, None]:
		"""Shared streaming logic for any OpenAI-compatible client."""
		kwargs = dict(**config, messages=messages, stream=True)
		if tools:
			kwargs["tools"] = tools
		if extra_headers:
			kwargs["extra_headers"] = extra_headers
		if extra_body:
			kwargs["extra_body"] = extra_body
		stream = client.chat.completions.create(**kwargs)
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
				for tc in tool_calls:
					yield ("tool_call", getattr(tc, "model_dump", lambda: tc)())
		yield ("done", None)

	def streamResponse(self, messages, tools=None) -> Generator[Tuple[str, Any], None, None]:
		"""Dispatch streaming to the correct provider based on project api setting."""
		if self.api == "openrouter":
			yield from self.streamResponseOpenRouter(messages, tools)
		else:
			yield from self.streamResponseOpenAI(messages, tools)

	def getResponse(self,messages,tools=None,tool_choice=None):
		uid = getattr(g, "uuid", None) if has_request_context() else None
		logger.info('USER %s SENDING THIS TO GPT: %s', uid, messages)
		try:
			if self.api == "openai":
				return self.getResponseOpenAI(messages,tools,tool_choice)
			if self.api == "azure":
				return self.getResponseAzure(messages,tools,tool_choice)
			if self.api == "openrouter":
				return self.getResponseOpenRouter(messages,tools,tool_choice)
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

	def saveUsage(self, response, user_id=None, topic=None,
				 purpose=None, service=None):
		prompt_tokens = response.usage.prompt_tokens
		completion_tokens = response.usage.completion_tokens
		model = self.config['model']
		api = self.api

		if user_id is None and has_request_context():
			user_id = getattr(g, "uuid", None)
		if topic is None and has_request_context():
			topic = getattr(g, "baseTopic", None)
		if purpose is None:
			if has_request_context():
				purpose = getattr(g, "llm_purpose", "chat")
			else:
				purpose = "analysis"
		if service is None:
			if has_request_context():
				service = getattr(g, "llm_service", "core")
			else:
				service = "batch"
		project_id = self.project

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
			logger.exception("Failed to record usage_stats")



	