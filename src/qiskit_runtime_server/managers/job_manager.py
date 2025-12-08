"""Job Manager with async queue and single worker."""

import json
import logging
import queue
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from qiskit_ibm_runtime.utils import RuntimeDecoder

from ..executors.base import BaseExecutor
from ..models import JobInfo, JobStatus
from ..providers.backend_metadata import get_backend_metadata_provider

logger = logging.getLogger(__name__)


class JobManager:
    """
    Manage job lifecycle with async queueing.

    Features:
    - Jobs are queued (FIFO)
    - Single worker thread processes jobs sequentially
    - Executor selection based on backend name
    - Thread-safe job state management
    """

    def __init__(self, executors: dict[str, BaseExecutor], session_manager: Any | None = None):
        """
        Initialize job manager with executors.

        Args:
            executors: Mapping of executor name to executor instance
                      Example: {"aer": AerExecutor(), "custatevec": CuStateVecExecutor()}
            session_manager: Optional SessionManager for session-aware job execution
        """
        self.executors = executors
        self.jobs: dict[str, JobInfo] = {}
        self._lock = threading.Lock()
        self._metadata_provider: Any = None
        self._session_manager = session_manager

        # Job queue (FIFO)
        self._queue: queue.Queue[str] = queue.Queue()

        # Worker thread
        self._worker_thread: threading.Thread | None = None
        self._shutdown_flag = threading.Event()

        # Start worker
        self._start_worker()

    @property
    def metadata_provider(self) -> Any:
        """Lazy-load metadata provider."""
        if self._metadata_provider is None:
            executor_names = list(self.executors.keys())
            self._metadata_provider = get_backend_metadata_provider(executor_names)
        return self._metadata_provider

    def _start_worker(self) -> None:
        """Start background worker thread."""
        if self._worker_thread is not None and self._worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return

        self._shutdown_flag.clear()
        self._worker_thread = threading.Thread(
            target=self._worker_loop, name="JobWorker", daemon=True
        )
        self._worker_thread.start()
        logger.info("Job worker thread started")

    def _worker_loop(self) -> None:
        """
        Worker thread main loop.

        Continuously polls the job queue and executes jobs sequentially.
        Only one job is executed at a time.
        """
        logger.info("Worker loop started")

        while not self._shutdown_flag.is_set():
            try:
                # Wait for next job (timeout to check shutdown flag)
                try:
                    job_id = self._queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # Execute job
                logger.info("Worker picked up job: %s", job_id)
                self._execute_job(job_id)

                # Mark task as done
                self._queue.task_done()

            except Exception as e:
                logger.error("Worker loop error: %s", e, exc_info=True)

        logger.info("Worker loop stopped")

    def create_job(
        self,
        program_id: str,
        backend_name: str,
        params: dict[str, Any],
        options: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> str:
        """
        Create a new job and add it to the queue.

        Args:
            program_id: Program to run ("sampler" or "estimator")
            backend_name: Backend name in "metadata@executor" format
            params: Job parameters (pubs, etc.)
            options: Execution options
            session_id: Optional session ID for session-aware execution

        Returns:
            Job ID

        Raises:
            ValueError: If backend_name format is invalid or session validation fails
        """
        # Validate backend name early
        parsed = self.metadata_provider.parse_backend_name(backend_name)
        if parsed is None:
            raise ValueError(f"Invalid backend name: {backend_name}")

        # Validate session if provided
        if session_id is not None and self._session_manager is not None:
            # Check if session exists
            session_info = self._session_manager.get_session(session_id)
            if session_info is None:
                raise ValueError(f"Session not found: {session_id}")

            # Validate backend matches session backend
            if not self._session_manager.validate_job_backend(session_id, backend_name):
                raise ValueError(
                    f"Backend mismatch: job backend '{backend_name}' "
                    f"does not match session backend '{session_info.backend_name}'"
                )

            # Check if session is accepting jobs
            if not session_info.accepting_jobs:
                raise ValueError(f"Session {session_id} is not accepting new jobs")

        # Generate job ID
        job_id = f"job-{uuid4()}"

        # Create job info
        job_info = JobInfo(
            job_id=job_id,
            program_id=program_id,
            backend_name=backend_name,
            params=params,
            options=options or {},
            session_id=session_id,
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        # Store job
        with self._lock:
            self.jobs[job_id] = job_info

        # Add job to session if provided
        if (
            session_id is not None
            and self._session_manager is not None
            and not self._session_manager.add_job_to_session(session_id, job_id)
        ):
            # Failed to add to session - clean up job
            with self._lock:
                del self.jobs[job_id]
            raise ValueError(f"Failed to add job to session {session_id}")

        # Add to queue
        self._queue.put(job_id)

        logger.info(
            "Job created and queued: %s (backend: %s, session: %s)",
            job_id,
            backend_name,
            session_id or "none",
        )
        return job_id

    def _execute_job(self, job_id: str) -> None:
        """
        Execute a job.

        This method is called by the worker thread.

        Args:
            job_id: Job ID to execute
        """
        # Get job info
        with self._lock:
            job_info = self.jobs.get(job_id)
            if job_info is None:
                logger.error("Job not found: %s", job_id)
                return
            if job_info.status == JobStatus.CANCELLED:
                logger.info("Job %s was cancelled, skipping execution", job_id)
                return
        try:
            # Update status: RUNNING
            with self._lock:
                job_info.status = JobStatus.RUNNING
                job_info.started_at = datetime.now(UTC)

            logger.info(
                "Executing job %s: %s on %s",
                job_id,
                job_info.program_id,
                job_info.backend_name,
            )

            # Parse backend name
            parsed = self.metadata_provider.parse_backend_name(job_info.backend_name)
            if parsed is None:
                raise ValueError(f"Invalid backend name: {job_info.backend_name}")
            metadata_name, executor_name = parsed

            # Get executor
            executor = self.executors.get(executor_name)
            if executor is None:
                raise ValueError(f"Executor not found: {executor_name}")

            deserialized_params = self._deserialize_params(job_info.params)

            # Execute via Executor interface
            if job_info.program_id == "sampler":
                result = executor.execute_sampler(
                    pubs=deserialized_params.get("pubs", []),
                    options=job_info.options,
                    backend_name=metadata_name,
                )
            elif job_info.program_id == "estimator":
                result = executor.execute_estimator(
                    pubs=deserialized_params.get("pubs", []),
                    options=job_info.options,
                    backend_name=metadata_name,
                )
            else:
                raise ValueError(f"Unknown program_id: {job_info.program_id}")

            # Update status: COMPLETED
            with self._lock:
                job_info.status = JobStatus.COMPLETED
                job_info.completed_at = datetime.now(UTC)
                job_info.result_data = result

            logger.info("Job completed: %s", job_id)

        except Exception as e:
            # Update status: FAILED
            logger.error("Job failed: %s: %s", job_id, e, exc_info=True)
            with self._lock:
                job_info.status = JobStatus.FAILED
                job_info.completed_at = datetime.now(UTC)
                job_info.error_message = str(e)

    def _deserialize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """
        Deserialize job parameters using RuntimeDecoder.

        Args:
            params: Serialized parameters from client

        Returns:
            Deserialized parameters ready for executor
        """
        # Use RuntimeDecoder to deserialize circuits and observables
        # RuntimeDecoder is used as object_hook in json.loads
        try:
            # Serialize to JSON string then deserialize with RuntimeDecoder
            json_str = json.dumps(params)
            deserialized: dict[str, Any] = json.loads(json_str, cls=RuntimeDecoder)
            return deserialized
        except Exception as e:
            logger.error("Failed to deserialize params: %s", e, exc_info=True)
            # Fallback: return params as-is
            return params

    def get_job(self, job_id: str) -> JobInfo | None:
        """
        Get job information.

        Args:
            job_id: Job ID

        Returns:
            JobInfo or None if not found
        """
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs(self) -> dict[str, JobInfo]:
        """
        List all jobs.

        Returns:
            Mapping of job_id to JobInfo
        """
        with self._lock:
            return dict(self.jobs)

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a job.

        Note: Only QUEUED jobs can be cancelled. RUNNING jobs cannot be interrupted.
        The job remains in the queue but is marked as CANCELLED. When the worker
        picks it up, it will be skipped.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled, False otherwise
        """
        with self._lock:
            job_info = self.jobs.get(job_id)
            if job_info is None:
                return False

            if job_info.status == JobStatus.QUEUED:
                job_info.status = JobStatus.CANCELLED
                job_info.completed_at = datetime.now(UTC)
                job_info.error_message = "Cancelled by user"
                return True

            return False

    def cancel_session_jobs(self, session_id: str) -> int:
        """
        Cancel all queued jobs in a session.

        Args:
            session_id: Session ID

        Returns:
            Number of jobs cancelled
        """
        cancelled_count = 0
        with self._lock:
            for job_info in self.jobs.values():
                if job_info.session_id == session_id and job_info.status == JobStatus.QUEUED:
                    job_info.status = JobStatus.CANCELLED
                    job_info.completed_at = datetime.now(UTC)
                    job_info.error_message = "Cancelled due to session cancellation"
                    cancelled_count += 1

        logger.info("Cancelled %d jobs from session %s", cancelled_count, session_id)
        return cancelled_count

    def get_queue_length(self, executor_name: str | None = None) -> int:
        """
        Get number of jobs in queue (QUEUED + RUNNING) for a specific executor.

        Args:
            executor_name: Optional executor name to filter by.
                          If None, returns total queue length for all executors.

        Returns:
            Number of queued or running jobs
        """
        with self._lock:
            if executor_name is None:
                # Return total count of QUEUED + RUNNING jobs
                return sum(
                    1
                    for job in self.jobs.values()
                    if job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
                )

            # Filter by executor name
            count = 0
            for job in self.jobs.values():
                if job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
                    continue

                # Parse backend name to get executor
                parsed = self.metadata_provider.parse_backend_name(job.backend_name)
                if parsed and parsed[1] == executor_name:
                    count += 1

            return count

    def shutdown(self) -> None:
        """Shutdown worker thread gracefully."""
        logger.info("Shutting down job manager...")
        self._shutdown_flag.set()

        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5.0)
            if self._worker_thread.is_alive():
                logger.warning("Worker thread did not stop in time")
            else:
                logger.info("Worker thread stopped")
