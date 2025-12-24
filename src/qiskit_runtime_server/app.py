"""FastAPI application factory."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from qiskit_ibm_runtime.utils import RuntimeEncoder

from .executors.base import BaseExecutor
from .managers.job_manager import JobManager
from .managers.session_manager import SessionManager
from .models import (
    JobCreateRequest,
    JobCreateResponse,
    JobState,
    JobStatus,
    JobStatusResponse,
    SessionCreateRequest,
    SessionResponse,
    SessionUpdateRequest,
)
from .providers.backend_metadata import BackendMetadataProvider

logger = logging.getLogger(__name__)


class BackendEncoder(json.JSONEncoder):
    """Custom JSON encoder for backend configuration.

    Converts Python objects to IBM Quantum API compatible JSON format:
    - complex numbers → [real, imag] arrays
    - datetime objects → ISO 8601 strings
    """

    def default(self, obj: Any) -> Any:
        if isinstance(obj, complex):
            return [obj.real, obj.imag]
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


def create_app(
    executors: dict[str, BaseExecutor] | None = None,
    statevector_num_qubits: int = 30,
) -> FastAPI:
    """
    Create FastAPI application with executor injection.

    Args:
        executors: Mapping of executor name to instance.
                  Defaults to {"aer": AerExecutor()}
        statevector_num_qubits: Number of qubits for statevector simulator.
                               Defaults to 30.

    Returns:
        FastAPI application instance
    """
    # Default to AerExecutor if not provided
    if executors is None:
        from .executors import AerExecutor

        executors = {"aer": AerExecutor()}

    # Extract executor names
    available_executors = list(executors.keys())

    # Create managers
    session_manager = SessionManager()
    job_manager = JobManager(executors=executors, session_manager=session_manager)
    metadata_provider = BackendMetadataProvider(available_executors, statevector_num_qubits)

    # Lifespan context manager for startup/shutdown
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Handle startup and shutdown events."""
        # Startup
        logger.info("=" * 60)
        logger.info("Qiskit Runtime Server starting...")
        logger.info("Available executors: %s", ", ".join(executors.keys()))
        logger.info("=" * 60)

        yield

        # Shutdown
        logger.info("Shutting down...")
        job_manager.shutdown()
        logger.info("Shutdown complete")

    # Create FastAPI app
    app = FastAPI(
        title="Qiskit Runtime Backend API",
        version="2025-05-01",
        lifespan=lifespan,
    )

    # Store managers in app state for access in endpoints
    app.state.job_manager = job_manager
    app.state.session_manager = session_manager
    app.state.metadata_provider = metadata_provider

    # ===== ENDPOINTS =====

    @app.get("/")
    async def root() -> dict[str, Any]:
        """Root endpoint."""
        return {
            "message": "Qiskit Runtime Backend API",
            "version": "2025-05-01",
            "executors": list(executors.keys()),
        }

    @app.get("/v1/backends")
    async def list_backends(fields: str | None = None) -> dict[str, Any]:
        """
        List all virtual backends (metadata × executor combinations).

        Args:
            fields: Optional field filter (not yet implemented)

        Returns:
            List of backends with metadata
        """
        response = metadata_provider.list_backends(fields)

        # Serialize with BackendEncoder to handle datetime and complex numbers
        json_str = json.dumps(response.model_dump(), cls=BackendEncoder)
        return json.loads(json_str)  # type: ignore[no-any-return]

    @app.get("/v1/backends/{backend_name}/configuration")
    async def get_backend_configuration(backend_name: str) -> dict[str, Any]:
        """
        Get configuration for a specific backend.

        Args:
            backend_name: Backend name in 'metadata@executor' format

        Returns:
            Backend configuration dict
        """
        # Parse backend name
        parsed = metadata_provider.parse_backend_name(backend_name)
        if not parsed:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found")

        metadata_name, _executor_name = parsed

        # Get backend (FakeProvider or statevector)
        try:
            backend = metadata_provider.get_backend(metadata_name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found") from e

        # Return configuration dict (same format as list_backends but for single backend)
        backend_dict = metadata_provider._backend_to_dict(backend)
        backend_dict["name"] = backend_name
        backend_dict["backend_name"] = backend_name

        # Serialize with BackendEncoder to handle datetime and complex numbers
        json_str = json.dumps(backend_dict, cls=BackendEncoder)
        return json.loads(json_str)  # type: ignore[no-any-return]

    @app.get("/v1/backends/{backend_name}/properties")
    async def get_backend_properties(backend_name: str) -> dict[str, Any]:
        """
        Get properties (calibration data) for a specific backend.

        Args:
            backend_name: Backend name in 'metadata@executor' format

        Returns:
            Backend properties dict with calibration data
        """
        # Parse backend name
        parsed = metadata_provider.parse_backend_name(backend_name)
        if not parsed:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found")

        metadata_name, _executor_name = parsed

        # Get backend (FakeProvider or statevector)
        try:
            backend = metadata_provider.get_backend(metadata_name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found") from e

        # Get properties from backend
        if hasattr(backend, "properties") and callable(backend.properties):
            properties = backend.properties()
            if properties and hasattr(properties, "to_dict"):
                # Get properties dict - contains datetime objects
                props_dict = properties.to_dict()

                # Override backend_name to use virtual backend name
                props_dict["backend_name"] = backend_name

                # Serialize with BackendEncoder to handle datetime objects
                json_str = json.dumps(props_dict, cls=BackendEncoder)
                return json.loads(json_str)  # type: ignore[no-any-return]

        # Properties not available - return 404
        raise HTTPException(
            status_code=404, detail=f"Properties not available for backend {backend_name}"
        )

    @app.get("/v1/backends/{backend_name}/status")
    async def get_backend_status(backend_name: str) -> dict[str, Any]:
        """
        Get backend operational status.

        For local simulation backends, always return active status.

        Args:
            backend_name: Backend name in 'metadata@executor' format

        Returns:
            Backend status information
        """
        # Parse and validate backend name
        parsed = metadata_provider.parse_backend_name(backend_name)
        if not parsed:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found")

        metadata_name, executor_name = parsed

        # Verify backend metadata exists
        try:
            metadata_provider.get_backend(metadata_name)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Backend {backend_name} not found") from e

        # Get queue length for this executor
        queue_length = job_manager.get_queue_length(executor_name)

        # Return active status for all local backends
        return {
            "state": True,
            "status": "active",
            "message": "",
            "length_queue": queue_length,
            "backend_version": "1.0.0",
        }

    @app.post("/v1/jobs", status_code=202)
    async def create_job(request: JobCreateRequest) -> JobCreateResponse:
        """
        Create a new job (async).

        The job is immediately queued and a job ID is returned.
        The client should poll the job status endpoint to check progress.

        Args:
            request: Job creation request

        Returns:
            Job ID (202 Accepted)

        Raises:
            HTTPException: If backend name is invalid
        """
        try:
            job_id = job_manager.create_job(
                program_id=request.program_id,
                backend_name=request.backend,
                params=request.params,
                options=request.options or {},
                session_id=request.session_id,
            )
            return JobCreateResponse(id=job_id, backend=request.backend)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/v1/jobs/{job_id}")
    async def get_job_status(job_id: str) -> JobStatusResponse:
        """
        Get job status.

        Args:
            job_id: Job ID

        Returns:
            Job status information

        Raises:
            HTTPException: If job not found
        """
        job_info = job_manager.get_job(job_id)
        if job_info is None:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobStatusResponse(
            id=job_info.job_id,
            state=JobState(
                status=job_info.status,
                reason=job_info.error_message,
            ),
            created_at=job_info.created_at,
            started_at=job_info.started_at,
            completed_at=job_info.completed_at,
        )

    @app.get("/v1/jobs/{job_id}/results")
    async def get_job_results(job_id: str) -> dict[str, Any]:
        """
        Get job results.

        Args:
            job_id: Job ID

        Returns:
            Job results (if completed)

        Raises:
            HTTPException: If job not found or not completed
        """
        job_info = job_manager.get_job(job_id)
        if job_info is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_info.status != JobStatus.COMPLETED:
            raise HTTPException(
                status_code=400, detail=f"Job is not completed (status: {job_info.status})"
            )

        if job_info.result_data is not None:
            try:
                json_str = json.dumps(job_info.result_data, cls=RuntimeEncoder)
                result: dict[str, Any] = json.loads(json_str)
                return result
            except Exception as e:
                logger.error("Failed to serialize results for job %s: %s", job_id, e, exc_info=True)
                raise HTTPException(
                    status_code=500, detail=f"Failed to serialize results: {e!s}"
                ) from e

        # No results available (shouldn't happen for COMPLETED jobs)
        raise HTTPException(status_code=404, detail="No results available")

    @app.delete("/v1/jobs/{job_id}")
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """
        Cancel a job.

        Note: Only QUEUED jobs can be cancelled. RUNNING jobs cannot be interrupted.

        Args:
            job_id: Job ID

        Returns:
            Cancellation status

        Raises:
            HTTPException: If job not found
        """
        success = job_manager.cancel_job(job_id)
        if not success:
            job_info = job_manager.get_job(job_id)
            if job_info is None:
                raise HTTPException(status_code=404, detail="Job not found")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job in {job_info.status} status",
            )

        return {"message": "Job cancelled"}

    # ===== SESSION ENDPOINTS =====

    @app.post("/v1/sessions", status_code=201)
    async def create_session(request: SessionCreateRequest) -> SessionResponse:
        """
        Create a new session.

        Sessions group jobs and control execution mode (dedicated/batch).

        Args:
            request: Session creation request

        Returns:
            Session information

        Raises:
            HTTPException: If backend name is invalid
        """
        # Validate backend name
        parsed = metadata_provider.parse_backend_name(request.backend)
        if not parsed:
            raise HTTPException(status_code=404, detail=f"Backend {request.backend} not found")

        # Create session
        session_id = session_manager.create_session(
            mode=request.mode,
            backend_name=request.backend,
            instance=request.instance,
            max_ttl=request.max_ttl,
        )

        # Return session response
        response = session_manager.get_session_response(session_id)
        if response is None:
            raise HTTPException(status_code=500, detail="Failed to create session")

        return response

    @app.get("/v1/sessions/{session_id}")
    async def get_session(session_id: str) -> SessionResponse:
        """
        Get session details.

        Args:
            session_id: Session ID

        Returns:
            Session information

        Raises:
            HTTPException: If session not found
        """
        response = session_manager.get_session_response(session_id)
        if response is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return response

    @app.patch("/v1/sessions/{session_id}")
    async def update_session(session_id: str, request: SessionUpdateRequest) -> SessionResponse:
        """
        Update session settings.

        Args:
            session_id: Session ID
            request: Session update request

        Returns:
            Updated session information

        Raises:
            HTTPException: If session not found
        """
        success = session_manager.update_session(session_id, request.accepting_jobs)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        response = session_manager.get_session_response(session_id)
        if response is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return response

    @app.delete("/v1/sessions/{session_id}/close", status_code=204)
    async def close_session(session_id: str) -> None:
        """
        Close a session gracefully.

        Stops accepting new jobs but allows running jobs to complete.

        Args:
            session_id: Session ID

        Raises:
            HTTPException: If session not found
        """
        success = session_manager.close_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

    @app.delete("/v1/sessions/{session_id}/cancel", status_code=204)
    async def cancel_session(session_id: str) -> None:
        """
        Cancel a session immediately.

        Stops accepting new jobs and cancels all queued jobs.

        Args:
            session_id: Session ID

        Raises:
            HTTPException: If session not found
        """
        # Cancel the session
        success = session_manager.cancel_session(session_id)
        if not success:
            raise HTTPException(status_code=404, detail="Session not found")

        # Cancel all queued jobs in the session
        job_manager.cancel_session_jobs(session_id)

    return app
