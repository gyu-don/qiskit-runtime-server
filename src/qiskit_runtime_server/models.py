"""Pydantic models for API requests and responses."""

from typing import Any

from pydantic import BaseModel


class BackendsResponse(BaseModel):
    """Response model for listing backends."""

    devices: list[dict[str, Any]]
