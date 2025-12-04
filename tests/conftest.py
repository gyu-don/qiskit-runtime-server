"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return standard authentication headers for testing."""
    return {
        "Authorization": "Bearer test-token",
        "Service-CRN": "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test",
        "IBM-API-Version": "2025-05-01",
    }
