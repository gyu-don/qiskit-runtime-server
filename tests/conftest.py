"""Pytest configuration and fixtures."""

from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest
from qiskit_ibm_runtime import QiskitRuntimeService


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Return standard authentication headers for testing."""
    return {
        "Authorization": "Bearer test-token",
        "Service-CRN": "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test",
        "IBM-API-Version": "2025-05-01",
    }


@contextmanager
def create_test_service(url: str):
    """Create QiskitRuntimeService for testing with authentication patching.

    This helper patches IBM Cloud authentication to allow connecting to a test server.
    Only for use in tests - DO NOT use in production code.

    Args:
        url: Test server URL (e.g., "http://127.0.0.1:18000")

    Yields:
        QiskitRuntimeService: Configured service instance
    """
    from qiskit_ibm_runtime.accounts.account import CloudAccount
    from qiskit_ibm_runtime.api.auth import CloudAuth

    instance_crn = "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test"

    # Patch CloudAccount.list_instances to return mock data
    original_list_instances = CloudAccount.list_instances

    def patched_list_instances(self) -> list[dict[str, Any]]:
        """Return mock instance data for testing."""
        if self.url and "127.0.0.1" in self.url:
            return [
                {
                    "crn": instance_crn,
                    "plan": "lite",
                    "name": "test-instance",
                }
            ]
        return original_list_instances(self)

    # Patch CloudAuth to bypass IAM authentication

    def patched_cloudauth_init(
        self, api_key, crn, private=False, proxies=None, verify=True
    ) -> None:
        """Skip IAM setup for localhost testing."""
        self.crn = crn
        self.api_key = api_key
        self.private = private
        self.proxies = proxies
        self.verify = verify
        self.tm = None  # Skip token manager for localhost

    def patched_get_headers(self) -> dict[str, str]:
        """Return simple headers without IAM token."""
        return {
            "Service-CRN": self.crn,
            "Authorization": f"Bearer {self.api_key}",
        }

    # Custom URL resolver that always returns our test server URL with /v1 prefix
    def mock_url_resolver(_base_url, _instance, _private_endpoint=False, _region=None) -> str:
        """Always return the test server URL with /v1 prefix."""
        return f"{url}/v1"

    # Apply patches
    with (
        patch.object(CloudAccount, "list_instances", patched_list_instances),
        patch.object(CloudAuth, "__init__", patched_cloudauth_init),
        patch.object(CloudAuth, "get_headers", patched_get_headers),
    ):
        # Create service with custom URL resolver
        service = QiskitRuntimeService(
            channel="ibm_cloud",
            url=url,
            token="test-token",
            instance=instance_crn,
            verify=False,
            url_resolver=mock_url_resolver,
        )

        yield service
