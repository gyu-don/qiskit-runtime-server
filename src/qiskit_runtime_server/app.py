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
from .models import (
    JobCreateRequest,
    JobCreateResponse,
    JobState,
    JobStatus,
    JobStatusResponse,
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


def create_app(executors: dict[str, BaseExecutor] | None = None) -> FastAPI:
    """
    Create FastAPI application with executor injection.

    Args:
        executors: Mapping of executor name to instance.
                  Defaults to {"aer": AerExecutor()}

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
    job_manager = JobManager(executors=executors)
    metadata_provider = BackendMetadataProvider(available_executors)

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

        # Get backend from FakeProvider
        backend = metadata_provider.provider.backend(metadata_name)

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

        # Get backend from FakeProvider
        backend = metadata_provider.provider.backend(metadata_name)

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
            metadata_provider.provider.backend(metadata_name)
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

    return app
