"""Session Manager for managing session lifecycle and job execution modes."""

import logging
import threading
from datetime import UTC, datetime
from uuid import uuid4

from ..models import SessionInfo, SessionMode, SessionResponse

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manage session lifecycle with dedicated and batch execution modes.

    Features:
    - Session creation with dedicated (sequential) or batch (parallel) modes
    - Session-scoped job tracking
    - Backend validation for session jobs
    - Session close and cancel operations
    - TTL tracking
    """

    def __init__(self) -> None:
        """Initialize session manager."""
        self.sessions: dict[str, SessionInfo] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        mode: SessionMode,
        backend_name: str,
        instance: str | None = None,
        max_ttl: int = 28800,
    ) -> str:
        """
        Create a new session.

        Args:
            mode: Session mode (dedicated or batch)
            backend_name: Backend name in "metadata@executor" format
            instance: IBM Cloud instance CRN (optional)
            max_ttl: Maximum time-to-live in seconds (default: 8 hours)

        Returns:
            Session ID
        """
        session_id = f"session-{uuid4()}"

        session_info = SessionInfo(
            session_id=session_id,
            mode=mode,
            backend_name=backend_name,
            instance=instance,
            max_ttl=max_ttl,
            created_at=datetime.now(UTC),
            accepting_jobs=True,
            active=True,
            job_ids=[],
        )

        with self._lock:
            self.sessions[session_id] = session_info

        logger.info(
            "Session created: %s (mode: %s, backend: %s)",
            session_id,
            mode,
            backend_name,
        )
        return session_id

    def get_session(self, session_id: str) -> SessionInfo | None:
        """
        Get session information.

        Args:
            session_id: Session ID

        Returns:
            SessionInfo or None if not found
        """
        with self._lock:
            return self.sessions.get(session_id)

    def get_session_response(self, session_id: str) -> SessionResponse | None:
        """
        Get session response with computed fields.

        Args:
            session_id: Session ID

        Returns:
            SessionResponse or None if not found
        """
        session_info = self.get_session(session_id)
        if session_info is None:
            return None

        # Calculate elapsed time
        elapsed_time = int((datetime.now(UTC) - session_info.created_at).total_seconds())

        return SessionResponse(
            id=session_info.session_id,
            mode=session_info.mode,
            backend=session_info.backend_name,
            instance=session_info.instance,
            max_ttl=session_info.max_ttl,
            created_at=session_info.created_at,
            accepting_jobs=session_info.accepting_jobs,
            active=session_info.active,
            elapsed_time=elapsed_time,
            jobs=list(session_info.job_ids),
        )

    def update_session(self, session_id: str, accepting_jobs: bool) -> bool:
        """
        Update session settings.

        Args:
            session_id: Session ID
            accepting_jobs: Whether the session should accept new jobs

        Returns:
            True if updated, False if session not found
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return False

            session_info.accepting_jobs = accepting_jobs
            logger.info("Session %s updated: accepting_jobs=%s", session_id, accepting_jobs)
            return True

    def close_session(self, session_id: str) -> bool:
        """
        Close a session gracefully.

        Stops accepting new jobs but allows running jobs to complete.

        Args:
            session_id: Session ID

        Returns:
            True if closed, False if session not found
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return False

            session_info.accepting_jobs = False
            session_info.active = False
            logger.info("Session closed: %s", session_id)
            return True

    def cancel_session(self, session_id: str) -> bool:
        """
        Cancel a session immediately.

        Stops accepting new jobs and marks session as inactive.
        Note: Cancelling queued jobs is handled by JobManager.

        Args:
            session_id: Session ID

        Returns:
            True if cancelled, False if session not found
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return False

            session_info.accepting_jobs = False
            session_info.active = False
            logger.info("Session cancelled: %s", session_id)
            return True

    def add_job_to_session(self, session_id: str, job_id: str) -> bool:
        """
        Add a job to a session.

        Args:
            session_id: Session ID
            job_id: Job ID to add

        Returns:
            True if added, False if session not found or not accepting jobs
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return False

            if not session_info.accepting_jobs:
                logger.warning(
                    "Session %s is not accepting jobs (accepting_jobs=%s)",
                    session_id,
                    session_info.accepting_jobs,
                )
                return False

            session_info.job_ids.append(job_id)
            logger.info("Job %s added to session %s", job_id, session_id)
            return True

    def validate_job_backend(self, session_id: str, backend_name: str) -> bool:
        """
        Validate that a job's backend matches the session's backend.

        Args:
            session_id: Session ID
            backend_name: Backend name to validate

        Returns:
            True if backend matches, False otherwise
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return False

            return session_info.backend_name == backend_name

    def get_session_mode(self, session_id: str) -> SessionMode | None:
        """
        Get the execution mode for a session.

        Args:
            session_id: Session ID

        Returns:
            SessionMode or None if session not found
        """
        with self._lock:
            session_info = self.sessions.get(session_id)
            if session_info is None:
                return None
            return session_info.mode

    def list_sessions(self) -> dict[str, SessionInfo]:
        """
        List all sessions.

        Returns:
            Mapping of session_id to SessionInfo
        """
        with self._lock:
            return dict(self.sessions)

    def cleanup_expired_sessions(self) -> int:
        """
        Clean up sessions that have exceeded their max_ttl.

        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now(UTC)
        expired_session_ids: list[str] = []

        with self._lock:
            for session_id, session_info in self.sessions.items():
                elapsed = (now - session_info.created_at).total_seconds()
                if elapsed > session_info.max_ttl:
                    expired_session_ids.append(session_id)

            for session_id in expired_session_ids:
                del self.sessions[session_id]
                logger.info("Expired session cleaned up: %s", session_id)

        return len(expired_session_ids)
