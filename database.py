import psycopg2
from psycopg2 import pool
# from pgvector.psycopg2 import register_vector
from flask import g
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

class DB:
	def __init__(self, config):
		try:
			self.postgreSQL_pool = psycopg2.pool.ThreadedConnectionPool(1, 8, **config)
			self.conn = None
			self.conn = self.postgreSQL_pool.getconn()
			# register_vector(self.conn)
		except (Exception, psycopg2.DatabaseError) as error:
			logger.exception("Error while connecting to PostgreSQL")
			raise

	def query_database_one(self, query, parameters):
		conn = self.conn
		cur = conn.cursor()
		try:
			cur.execute(query, parameters)
			results = cur.fetchone()
			cur.close()
			return results
		except psycopg2.DatabaseError as e:
			conn.rollback()
			cur.close()
			print(f"Database error: {e}")
			print("Exception Type:", type(e))
			print("Exception Args:", e.args)
			print("Exception PGCODE:", e.pgcode)
			print("Exception PGERROR:", e.pgerror)
			print("Exception DIAG:", e.diag.message_primary)
			raise
		except Exception as e:
			print(f"An error occurred while selecting one: {e}")
			conn.rollback()
			cur.close()
			raise

	def query_database_all(self, query, parameters):
		conn = self.conn
		cur = conn.cursor()
		try:
			cur.execute(query, parameters)
			results = cur.fetchall()
			cur.close()
			return results
		except psycopg2.DatabaseError as e:
			conn.rollback()
			cur.close()
			print(f"Database error: {e}")
			print("Exception Type:", type(e))
			print("Exception Args:", e.args)
			print("Exception PGCODE:", e.pgcode)
			print("Exception PGERROR:", e.pgerror)
			print("Exception DIAG:", e.diag.message_primary)
			raise
		except Exception as e:
			print(f"An error occurred while selecting all: {e}")
			conn.rollback()
			cur.close()
			raise
	
	def query_database_insert(self, query, parameters):
		conn = self.conn
		cur = conn.cursor()
		try:
			cur.execute(query, parameters)
			conn.commit()
			cur.close()
		except psycopg2.DatabaseError as e:
			conn.rollback()
			cur.close()
			print(f"Database error: {e}")
			print("Exception Type:", type(e))
			print("Exception Args:", e.args)
			print("Exception PGCODE:", e.pgcode)
			print("Exception PGERROR:", e.pgerror)
			print("Exception DIAG:", e.diag.message_primary)
			raise
		except Exception as e:
			print(f"An error occurred while inserting: {e}")
			conn.rollback()
			cur.close()
			raise
				
	def close(self):
		self.postgreSQL_pool.closeall()

	def get_records(self,uuid,project):
		query = "SELECT created_at,role,content,topic FROM records WHERE user_id=%s AND project=%s ORDER by created_at ASC"
		query_params = (uuid,project)
		results = self.query_database_all(query,query_params)
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

	def store_message(self,role,message,voice_input=False,audio_tokens=0):
		now = datetime.now(timezone.utc)
		if role == 'user':
			topic = g.baseTopic
		else:
			topic = g.topic
		voice_flag = bool(voice_input)
		token_count = int(audio_tokens or 0)
		if role == 'user':
			voice_flag = bool(getattr(g, "voice_input", voice_flag))
			token_count = int(getattr(g, "audio_tokens", token_count) or 0)
		else:
			voice_flag = False
			token_count = 0
		query = "INSERT INTO records (created_at,project,role,content,topic,user_id,voice_input,audio_tokens) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
		query_params = (now,g.projectId,role,message,topic,g.uuid,voice_flag,token_count)
		logger.debug('===Topic ID (message storing) (role: %s)===: %s', role, topic)
		try:
			self.query_database_insert(query,query_params)
		except Exception as e:
			err_text = str(e)
			if "voice_input" in err_text or "audio_tokens" in err_text:
				fallback_query = "INSERT INTO records (created_at,project,role,content,topic,user_id) VALUES (%s,%s,%s,%s,%s,%s)"
				fallback_params = (now,g.projectId,role,message,topic,g.uuid)
				self.query_database_insert(fallback_query,fallback_params)
			else:
				raise
		if role == 'user':
			setattr(g, "voice_input", False)
			setattr(g, "audio_tokens", 0)
