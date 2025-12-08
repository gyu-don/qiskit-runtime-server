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
    session_id: str | None = None  # Optional session association

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
    session_id: str | None = None  # Optional session ID


class JobCreateResponse(BaseModel):
    """Response model for job creation."""

    id: str
    backend: str


class JobState(BaseModel):
    """Job state nested object for IBM API compatibility."""

    status: JobStatus
    reason: str | None = None


class JobStatusResponse(BaseModel):
    """Response model for job status."""

    id: str
    state: JobState
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class JobResultResponse(BaseModel):
    """Response model for job result."""

    id: str
    status: JobStatus
    results: Any | None = None
    error_message: str | None = None


# Session Models


class SessionMode(StrEnum):
    """Session execution mode."""

    DEDICATED = "dedicated"  # Sequential job execution
    BATCH = "batch"  # Parallel job execution


class SessionInfo(BaseModel):
    """Internal session information."""

    session_id: str
    mode: SessionMode
    backend_name: str  # "fake_manila@aer" format
    instance: str | None = None
    max_ttl: int  # Maximum time-to-live in seconds

    # Status tracking
    created_at: datetime
    accepting_jobs: bool = True
    active: bool = True
    job_ids: list[str] = []  # Track jobs in this session


class SessionCreateRequest(BaseModel):
    """Request model for creating a session."""

    mode: SessionMode
    backend: str  # "metadata@executor" format
    instance: str | None = None
    max_ttl: int = 28800  # Default: 8 hours


class SessionResponse(BaseModel):
    """Response model for session information."""

    id: str
    mode: SessionMode
    backend: str
    instance: str | None = None
    max_ttl: int
    created_at: datetime
    accepting_jobs: bool
    active: bool
    elapsed_time: int  # Seconds since creation
    jobs: list[str]


class SessionUpdateRequest(BaseModel):
    """Request model for updating a session."""

    accepting_jobs: bool
