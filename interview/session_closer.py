"""Close stale interview sessions based on inactivity.

Runs as a before_request hook for endpoints that require a DB connection.
Pending Phase 1: accepts db as parameter; still reads project_id from Flask
request headers for backwards compatibility.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from flask import request

logger = logging.getLogger(__name__)


class SessionInactivityCloser:
    @staticmethod
    def _inactive_minutes() -> int:
        from config import cfg
        return cfg.session_inactivity_minutes

    @staticmethod
    def _project_id_from_request() -> Optional[str]:
        header_id = (request.headers.get("projectId") or "").strip()
        if header_id:
            return header_id
        path = (request.path or "").strip("/")
        parts = path.split("/")
        if len(parts) >= 4 and parts[0] == "api" and parts[1] == "admin" and parts[2] == "projects":
            return parts[3]
        return None

    @staticmethod
    def close_stale_sessions(db, *, requires_db_fn=None) -> None:
        """Close sessions inactive beyond the configured threshold.

        Parameters
        ----------
        db : DB
            Database instance (typically ``g.db``).
        requires_db_fn : callable, optional
            Guard function returning False when the current request does not
            need a DB.  When omitted the check is skipped.
        """
        if requires_db_fn and not requires_db_fn():
            return
        if db is None:
            return
        project_id = SessionInactivityCloser._project_id_from_request()
        if not project_id:
            return
        minutes = SessionInactivityCloser._inactive_minutes()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        q = """
          WITH latest AS (
            SELECT tl.user_id, MAX(tl.started_at) AS last_started
            FROM topics_log tl
            JOIN respondents r ON r.id = tl.user_id AND r.project = %s
            WHERE tl.status = 1
            GROUP BY tl.user_id
          ),
          last_input AS (
            SELECT user_id, MAX(created_at) AS last_user_at
            FROM records
            WHERE project=%s AND role='user'
            GROUP BY user_id
          )
          UPDATE topics_log tl
          SET status=0
          FROM latest l
          LEFT JOIN last_input li ON li.user_id = l.user_id
          WHERE tl.user_id = l.user_id
            AND tl.started_at = l.last_started
            AND tl.status = 1
            AND COALESCE(li.last_user_at, tl.started_at) <= %s
        """
        try:
            db.query_database_insert(q, (project_id, project_id, cutoff))
        except Exception:
            logger.exception("Failed to close inactive sessions for project %s", project_id)
