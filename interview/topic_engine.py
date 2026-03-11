"""Topic state machine for interview sessions.

Merges the former ``topic.py`` (TopicEngine, née topicHandler) and
``autoTopic.py`` (tool spec + LLM tool-call handling) into a single module.
"""

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from drawscape_factorio import DrawscapeFactorio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Raw tool-call text helper (shared with conversation / reply_handler)
# ---------------------------------------------------------------------------

_RAW_TOOL_CALL_RE = re.compile(
    r'interview_topic_over\s*\(\s*\{[^}]*\}\s*\)\s*', re.IGNORECASE
)


def strip_raw_tool_text(text: str) -> str:
    """Remove raw interview_topic_over(...) text the model sometimes emits."""
    if not text:
        return text
    return _RAW_TOOL_CALL_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# LLM tool spec for auto-topic switching
# ---------------------------------------------------------------------------

TOOL_SPEC = [
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


def _propagate_topic_switch(new_topic_id):
    """Bridge: update ``g.*`` after a topic switch until all callers are migrated."""
    if new_topic_id is None:
        return
    try:
        from flask import g, has_request_context
        if has_request_context():
            g.topic = new_topic_id
            g.topicIsChanging = True
    except Exception:
        pass


def handle_tool_call(response, topic_engine=None):
    """Dispatch an LLM tool-call response to trigger a topic switch.

    Parameters
    ----------
    response : LLM response object
    topic_engine : TopicEngine, optional
        Explicit topic engine instance.  Falls back to ``g.th`` when omitted.

    Returns the next topic id on success, or None.
    """
    response_message = response.choices[0].message
    if response_message.tool_calls:
        if topic_engine is None:
            from flask import g
            topic_engine = g.th
        available_functions = {"interview_topic_over": topic_engine.forceSwitchTopic}
        function_name = response_message.tool_calls[0].function.name
        function_to_call = available_functions[function_name]
        result = function_to_call()
        _propagate_topic_switch(result)
        return result
    return None


def force_switch_from_text(th):
    """Trigger topic switch when the model emitted interview_topic_over as
    plain text instead of a proper tool_call."""
    result = th.forceSwitchTopic()
    _propagate_topic_switch(result)
    return result


# ---------------------------------------------------------------------------
# TopicEngine (formerly topicHandler)
# ---------------------------------------------------------------------------

class TopicEngine:
    def __init__(self, db=None, project_id=None, user_id=None):
        if project_id is not None:
            self.project = project_id
        else:
            from flask import g
            self.project = g.projectId

        if user_id is not None:
            self.uuid = user_id
        else:
            from flask import g
            self.uuid = g.uuid

        if db is not None:
            self.DB = db
        else:
            from flask import g
            self.DB = g.db

        self.topics = self.getTopics()
        self.topic = self.getCurrentTopic()

    def getTopics(self):
        query = "SELECT id,system,length FROM topics WHERE project=%s ORDER by sequence ASC"
        query_params = (self.project,)
        results = self.DB.query_database_all(query, query_params)
        topic_no = 0
        topics = []
        for row in results:
            topic_no += 1
            topic_row = (topic_no, row[0], row[1], row[2])
            topics.append(topic_row)
        return topics

    def getTopicsLog(self):
        query = "SELECT id,topic_id,started_at,status,responses FROM topics_log WHERE user_id=%s ORDER by started_at ASC"
        query_params = (self.uuid,)
        results = self.DB.query_database_all(query, query_params)
        topic_no = 0
        topics = []
        for row in results:
            topic_no += 1
            topic_row = (topic_no, row[0], row[1], row[2], row[3], row[4])
            topics.append(topic_row)
        return topics

    def getTopicProgress(self):
        total = DrawscapeFactorio.normalize_tokens(len(self.topics))
        if total <= 0:
            return {"current": 0, "total": 0, "ratio": 0}
        current_topic_id = self.getCurrentTopic()
        current_row = self.findTopicById(current_topic_id)
        current_no = DrawscapeFactorio.normalize_tokens(current_row[0] if current_row else 0)
        if current_no < 0:
            current_no = 0
        if current_no > total:
            current_no = total
        ratio = current_no / total if total else 0
        return {"current": current_no, "total": total, "ratio": ratio}

    def getCurrentTopic(self):
        topics_log = self.getTopicsLog()
        if len(topics_log) == 0:
            logger.debug('===Returning Topic ID as current (initial):===: %s', self.topics[0][1])
            return self.topics[0][1]
        else:
            logger.debug('===Returning Topic ID as current:===: %s', topics_log[-1][2])
            return topics_log[-1][2]

    def getSwitchStrategy(self):
        query = "SELECT expiration_strategy FROM topics WHERE id=%s"
        query_params = (self.topic,)
        results = self.DB.query_database_one(query, query_params)[0]
        return results

    def getTopicType(self, topic):
        query = "SELECT topic_type FROM topics WHERE id=%s"
        query_params = (topic,)
        results = self.DB.query_database_one(query, query_params)[0]
        return results

    def findTopicById(self, topic_id):
        topics = self.topics
        for row in topics:
            if row[1] == topic_id:
                return row

    def findTopicByNo(self, number):
        topics = self.topics
        for row in topics:
            if row[0] == number:
                return row

    def findTopicLogEntry(self, topic_id):
        topics_log = self.getTopicsLog()
        for row in topics_log:
            if row[2] == topic_id:
                return row

    def isTopicExpired(self, response_count=None):
        if response_count is None:
            from flask import g
            response_count = g.response_count
        topic = self.findTopicById(self.getCurrentTopic())
        topics_log = self.getTopicsLog()
        topic_response_treshold = topic[3]
        current_time = datetime.now(timezone.utc)

        if self.getTopicType(self.topic) == "single_question" and response_count > 0:
            return True

        if self.getTopicType(self.topic) == "auto":
            if self.getSwitchStrategy() == "count":
                if response_count >= topic_response_treshold:
                    return True
            return None

        elif self.getSwitchStrategy() == "time":
            if topics_log:
                topic_start_time = topics_log[-1][3]
            else:
                topic_start_time = current_time

            topic_expiration_date = timedelta(seconds=topic[3]) * 60 + topic_start_time
            logger.debug('Topic expiration time: %s', topic_expiration_date)

            if topic_expiration_date > current_time:
                return None
            else:
                return True

        elif self.getSwitchStrategy() == "count":
            logger.debug('===Comparing responses and limit:===: %s/%s', response_count, topic_response_treshold)

            if response_count >= topic_response_treshold:
                return True
            else:
                return None
        else:
            return None

    def getNextTopic(self):
        current_topic = self.findTopicById(self.topic)
        if current_topic[0] < len(self.topics):
            next_topic = self.findTopicByNo(current_topic[0] + 1)
            return next_topic[1]
        else:
            return None

    def makeNewTopicLogEntry(self, topic_id):
        query = "INSERT into topics_log (topic_id,user_id,started_at,status,responses) VALUES (%s,%s,%s,%s,%s)"
        params = (topic_id, self.uuid, datetime.now(timezone.utc), 1, 0)
        self.DB.query_database_insert(query, params)

    def changeLogEntryStatus(self):
        query = "UPDATE topics_log set status=0 where topic_id=%s AND user_id=%s"
        params = (self.topic, self.uuid)
        self.DB.query_database_insert(query, params)

    def switchTopic(self, response_count=None) -> Tuple[str, bool]:
        """Advance the topic state machine.

        Returns ``(topic_id, is_changing)`` where *is_changing* indicates
        whether a topic transition happened on this call.
        """
        if response_count is None:
            from flask import g
            response_count = getattr(g, 'response_count', 0)

        topics_log = self.getTopicsLog()
        total_topic_count = self.topics[-1][0]

        if topics_log:
            covered_topic_count = topics_log[-1][0]
        else:
            covered_topic_count = 0

        if covered_topic_count == 0 and self.uuid is not None:
            self.makeNewTopicLogEntry(self.topic)
            logger.debug('===Making new topic log entry (new topic): %s for user: %s', self.topic, self.uuid)
            return (self.topic, True)

        elif self.isTopicExpired(response_count) == True and total_topic_count > covered_topic_count:
            next_topic = self.getNextTopic()
            self.changeLogEntryStatus()
            self.makeNewTopicLogEntry(next_topic)
            logger.debug('===Making new topic log entry (expired topic): %s for user: %s because topic is: %s', next_topic, self.uuid, self.isTopicExpired(response_count))
            return (next_topic, True)

        elif self.isTopicExpired(response_count) and total_topic_count == covered_topic_count:
            self.changeLogEntryStatus()
            return (self.topic, False)
        else:
            return (self.topic, False)

    def updateResponseCounter(self, base_topic=None, user_id=None):
        if base_topic is None:
            from flask import g
            base_topic = g.baseTopic
        if user_id is None:
            user_id = self.uuid
        query = "select count(*) from records where topic=%s AND role='user' AND user_id=%s"
        params = (base_topic, user_id)
        result = self.DB.query_database_one(query, params)
        logger.debug('===Topic ID (counter update):===: %s', base_topic)
        query_update = "update topics_log set responses=%s where topic_id=%s and user_id=%s"
        self.DB.query_database_insert(query_update, (result, base_topic, user_id))
        return result

    def forceSwitchTopic(self):
        """Force an immediate topic switch (used by auto-topic tool calls).

        Returns the new topic_id on success, or None when no more topics.
        Updates ``self.topic`` but does NOT mutate ``g.*``.
        """
        if self.getNextTopic():
            next_topic = self.getNextTopic()
            self.changeLogEntryStatus()
            self.makeNewTopicLogEntry(next_topic)
            logger.debug('===Making new topic log entry (by auto-switch): %s for user: %s', next_topic, self.uuid)
            self.topic = next_topic
            return next_topic
        else:
            self.changeLogEntryStatus()
            return None


# Backward-compatible alias
topicHandler = TopicEngine
