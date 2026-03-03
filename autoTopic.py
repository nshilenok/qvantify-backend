from flask import g

function = [
	{
		"type": "function",
		"function": {
			"name": "interview_topic_over",
			"description": "Call only when CURRENT TOPIC is complete and ready to switch.",
			"strict": True,
			"parameters": {
				"type": "object",
				"additionalProperties": False,
				"properties": {
					"status": {
						"type": "string",
						"enum": ["done"],
						"description": "Topic status. done means the topic has sufficient user information."
					}
				},
				"required": ["status"]
			}
		}
	}
]

def switchTopic(response):
	response_message = response.choices[0].message
	if response_message.tool_calls:
		available_functions = {"interview_topic_over": g.th.forceSwitchTopic,}
		function_name = response_message.tool_calls[0].function.name
		function_to_call = available_functions[function_name]
		function_response = function_to_call()
		return function_response

def forceSwitchFromText(th):
	"""Trigger topic switch when the model emitted interview_topic_over as
	plain text instead of a proper tool_call."""
	return th.forceSwitchTopic()