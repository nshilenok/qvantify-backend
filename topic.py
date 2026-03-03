from flask import g
from datetime import datetime, timezone, timedelta
import logging
from drawscape_factorio import DrawscapeFactorio

logger = logging.getLogger(__name__)


class topicHandler():
	def __init__(self,db=None):
		self.project =  g.projectId
		self.uuid =  g.uuid
		self.DB = g.db
		self.topics = self.getTopics()
		self.topic = self.getCurrentTopic()

	def getTopics(self):
		query = "SELECT id,system,length FROM topics WHERE project=%s ORDER by sequence ASC"
		query_params = (self.project,)
		results = self.DB.query_database_all(query,query_params)
		topic_no = 0
		topics = []
		for row in results:
			topic_no += 1
			topic_row = (
			topic_no,
			row[0],
			row[1],
			row[2]
			)
			topics.append(topic_row)
		return topics

	def getTopicsLog(self):
		query = "SELECT id,topic_id,started_at,status,responses FROM topics_log WHERE user_id=%s ORDER by started_at ASC"
		query_params = (self.uuid,)
		results = self.DB.query_database_all(query,query_params)
		topic_no = 0
		topics = []
		for row in results:
			topic_no += 1
			topic_row = (
			topic_no,
			row[0],
			row[1],
			row[2],
			row[3],
			row[4]
			)
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
		results = self.DB.query_database_one(query,query_params)[0]
		return results

	def getTopicType(self,topic):
		query = "SELECT topic_type FROM topics WHERE id=%s"
		query_params = (topic,)
		results = self.DB.query_database_one(query,query_params)[0]
		return results

	def findTopicById(self,topic_id):
		topics = self.topics
		for row in topics:
			if row[1] == topic_id:
				return row

	def findTopicByNo(self,number):
		topics = self.topics
		for row in topics:
			if row[0] == number:
				return row

	def findTopicLogEntry(self,topic_id):
		topics_log = self.getTopicsLog()
		for row in topics_log:
			if row[2] == topic_id:
				return row


	def isTopicExpired(self):
		topic = self.findTopicById(self.getCurrentTopic())
		topics_log = self.getTopicsLog()
		topic_response_treshold = topic[3]
		current_time = datetime.now(timezone.utc)
		response_count = g.response_count

		if self.getTopicType(self.topic) == "single_question" and response_count > 0:
			return True

		if self.getTopicType(self.topic) == "auto":
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
			logger.debug('===Comparing responses and limit:===: %s/%s', response_count,topic_response_treshold)
			
			if response_count >= topic_response_treshold:
				return True
			else:
				return None
		else:
			return None


	def getNextTopic(self):
		current_topic = self.findTopicById(self.topic)
		if current_topic[0] < len(self.topics):
			next_topic = self.findTopicByNo(current_topic[0]+1)
			return next_topic[1]
		else:
			return None

	def makeNewTopicLogEntry(self,topic_id):
		query = "INSERT into topics_log (topic_id,user_id,started_at,status,responses) VALUES (%s,%s,%s,%s,%s)"
		params =(topic_id,g.uuid,datetime.now(timezone.utc),1,0)
		g.db.query_database_insert(query,params)

	def changeLogEntryStatus(self):
		query = "UPDATE topics_log set status=0 where topic_id=%s AND user_id=%s"
		params = (self.topic, self.uuid)
		result = g.db.query_database_insert(query,params)


	def switchTopic(self):
		topics_log = self.getTopicsLog()
		total_topic_count = self.topics[-1][0]

		if topics_log:
			covered_topic_count = topics_log[-1][0]
		else:
			covered_topic_count = 0

		
		if covered_topic_count == 0 and g.uuid is not None:
			self.makeNewTopicLogEntry(self.topic)
			logger.debug('===Making new topic log entry (new topic): %s for user: %s', self.topic, g.uuid )
			g.topicIsChanging = True
			return self.topic

		elif self.isTopicExpired() == True and total_topic_count > covered_topic_count:
			next_topic=self.getNextTopic()
			self.changeLogEntryStatus()
			self.makeNewTopicLogEntry(next_topic)
			logger.debug('===Making new topic log entry (expired topic): %s for user: %s because topic is: %s', next_topic, g.uuid, self.isTopicExpired())
			g.topicIsChanging = True
			return next_topic

		elif self.isTopicExpired() and total_topic_count == covered_topic_count:
			self.changeLogEntryStatus()
			return self.topic
		else:
			return self.topic

	def updateResponseCounter(self):
		query = "select count(*) from records where topic=%s AND role='user' AND user_id=%s"
		params = (g.baseTopic,g.uuid)
		result = g.db.query_database_one(query,params)
		logger.debug('===Topic ID (counter update):===: %s', g.baseTopic)
		query_update = "update topics_log set responses=%s where topic_id=%s and user_id=%s"
		g.db.query_database_insert(query_update,(result,g.baseTopic,g.uuid))
		return result
	
	def forceSwitchTopic(self):
		if self.getNextTopic():
			next_topic = self.getNextTopic()
			self.changeLogEntryStatus()
			self.makeNewTopicLogEntry(next_topic)
			logger.debug('===Making new topic log entry (by auto-switch): %s for user: %s', next_topic, g.uuid )
			self.topic = next_topic
			g.topicIsChanging = True
			g.topic = next_topic
			return next_topic
		else:
			self.changeLogEntryStatus()
			return None