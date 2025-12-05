"""FastAPI application factory."""

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from qiskit_ibm_runtime.utils import RuntimeEncoder

from .executors.base import BaseExecutor
from .managers.job_manager import JobManager
from .models import (
    BackendsResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobStatusResponse,
)
from .providers.backend_metadata import get_backend_metadata_provider

logger = logging.getLogger(__name__)


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
    metadata_provider = get_backend_metadata_provider(available_executors)

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
    async def list_backends(fields: str | None = None) -> BackendsResponse:
        """
        List all virtual backends (metadata × executor combinations).

        Args:
            fields: Optional field filter (not yet implemented)

        Returns:
            List of backends with metadata
        """
        response = metadata_provider.list_backends(fields)
        return response

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
            return JobCreateResponse(id=job_id)
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
            status=job_info.status,
            created_at=job_info.created_at,
            started_at=job_info.started_at,
            completed_at=job_info.completed_at,
            error_message=job_info.error_message,
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

        # Serialize results using RuntimeEncoder
        results_data = None
        if job_info.result_data is not None:
            try:
                # Use RuntimeEncoder to properly serialize PrimitiveResult
                # This handles QuantumCircuit, Observables, and PrimitiveResult
                json_str = json.dumps(job_info.result_data, cls=RuntimeEncoder)
                results_data = json.loads(json_str)
            except Exception as e:
                logger.error("Failed to serialize results for job %s: %s", job_id, e, exc_info=True)
                results_data = {"error": "Failed to serialize results", "details": str(e)}

        return {
            "id": job_info.job_id,
            "status": job_info.status,
            "results": results_data,
            "error_message": job_info.error_message,
        }

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
