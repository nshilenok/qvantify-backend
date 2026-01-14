import credentials
import openai
from openai import AzureOpenAI
from openai import OpenAI
from flask import g
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
		query = "select model,temperature,max_tokens,top_p,api from projects where id=%s"
		query_params = (self.project,)
		response = self.DB.query_database_one(query,query_params)
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
			config = {key: value if value is not None else default_values[key] for key, value in zip(default_values.keys(), response)}
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

	def getResponseAzure(self,messages,tools=None):
		config = self.config
		os.environ["AZURE_OPENAI_API_KEY"] = credentials.azureopenai_key
		client = AzureOpenAI(api_version="2023-09-01-preview",azure_endpoint="https://qvantify-se.openai.azure.com")
		if tools:
			response = client.chat.completions.create(**config,messages=messages,tools=tools)
		else:
			response = client.chat.completions.create(**config,messages=messages)
		logger.debug('==========================Azure Output===========================: %s', response)
		self.saveUsage(response)
		client.close()
		return response


	def getResponseOpenAI(self,messages,tools=None):
		config = self.config
		os.environ["OPENAI_API_KEY"] = self.key
		client = OpenAI() 
		if tools:
			response = client.chat.completions.create(**config,messages=messages,tools=tools)
		else:
			response = client.chat.completions.create(**config,messages=messages)
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

	def getResponse(self,messages,tools=None):
		logger.info('USER %s SENDING THIS TO GPT: %s', g.uuid, messages)
		try:
			if self.api == "openai":
				return self.getResponseOpenAI(messages,tools)
			if self.api == "azure":
				return self.getResponseAzure(messages,tools)
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
		query = "INSERT INTO usage_stats (prompt_tokens, completion_tokens, user_id, project, topic, api, model) values (%s, %s, %s, %s, %s, %s, %s)"
		params = (prompt_tokens, completion_tokens, g.uuid, g.projectId, g.baseTopic, api, model)
		self.DB.query_database_insert(query, params)



	