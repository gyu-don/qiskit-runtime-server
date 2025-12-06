"""Pydantic models for API requests and responses."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class BackendsResponse(BaseModel):
    """Response model for listing backends."""

    devices: list[dict[str, Any]]


class JobStatus(StrEnum):
    """Job status."""

    QUEUED = "QUEUED"  # Job is queued and waiting to execute
    RUNNING = "RUNNING"  # Job is currently executing
    COMPLETED = "COMPLETED"  # Job completed successfully
    FAILED = "FAILED"  # Job failed with an error
    CANCELLED = "CANCELLED"  # Job was cancelled by user


class JobInfo(BaseModel):
    """Internal job information."""

    job_id: str
    program_id: str
    backend_name: str  # "fake_manila@aer" format
    params: dict[str, Any]
    options: dict[str, Any]

    # Status tracking
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Results
    result_data: Any | None = None  # PrimitiveResult
    error_message: str | None = None


# API Request/Response Models


class JobCreateRequest(BaseModel):
    """Request model for creating a job."""

    program_id: str
    backend: str  # "metadata@executor" format
    params: dict[str, Any]
    options: dict[str, Any] | None = None


class JobCreateResponse(BaseModel):
    """Response model for job creation."""

    id: str


class JobStatusResponse(BaseModel):
    """Response model for job status."""

    id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class JobResultResponse(BaseModel):
    """Response model for job result."""

    id: str
    status: JobStatus
    results: Any | None = None
    error_message: str | None = None
