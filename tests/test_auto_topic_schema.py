import autoTopic


def test_interview_topic_over_tool_schema_is_strict():
    assert autoTopic.function, "autoTopic.function must define at least one tool"
    tool = autoTopic.function[0]
    fn = tool["function"]

    assert fn["name"] == "interview_topic_over"
    assert fn["strict"] is True

    params = fn["parameters"]
    assert params["type"] == "object"
    assert params["additionalProperties"] is False
    assert params["required"] == ["status"]
    assert params["properties"]["status"]["enum"] == ["done"]
