"""Standalone helper for connecting QiskitRuntimeService to local server.

This standalone script can be copied to any project and used without installing
the qiskit-runtime-server package. It patches authentication flows to allow
connecting the official qiskit-ibm-runtime client to a local server.

Usage:
    # Copy this file to your project, then:
    from local_service_helper import local_service_connection

    with local_service_connection("http://localhost:8000") as service:
        backends = service.backends()
        backend = service.backend("fake_manila@aer")
        # ... use service normally

WARNING: These utilities bypass IBM Cloud authentication and should only be used
for local development and testing with self-hosted servers.
"""

from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from qiskit_ibm_runtime import QiskitRuntimeService


@contextmanager
def local_service_connection(
    url: str,
    token: str = "test-token",
    instance: str = "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test",
    verify: bool = False,
):
    """Create QiskitRuntimeService connected to local server with auth patching.

    This context manager patches the IBM Cloud authentication flow to allow
    connecting to a local server without IBM Cloud credentials.

    Args:
        url: Local server URL (e.g., "http://localhost:8000")
        token: Mock token (not validated by local server)
        instance: Mock CRN instance identifier
        verify: SSL verification (typically False for localhost)

    Yields:
        QiskitRuntimeService: Configured service instance

    Example:
        >>> with local_service_connection("http://localhost:8000") as service:
        ...     backends = service.backends()
        ...     backend = service.backend("fake_manila@aer")
        ...     sampler = SamplerV2(mode=backend)
        ...     job = sampler.run([circuit])
        ...     result = job.result()
    """
    from qiskit_ibm_runtime.accounts.account import CloudAccount
    from qiskit_ibm_runtime.api.auth import CloudAuth

    # Patch CloudAccount.list_instances to return mock data
    original_list_instances = CloudAccount.list_instances

    def patched_list_instances(self) -> list[dict[str, Any]]:
        """Return mock instance data for local testing."""
        # Check if URL is localhost/127.0.0.1
        if self.url and ("127.0.0.1" in self.url or "localhost" in self.url):
            return [
                {
                    "crn": instance,
                    "plan": "lite",
                    "name": "test-instance",
                }
            ]
        # Otherwise use original implementation
        return original_list_instances(self)

    # Patch CloudAuth to bypass IAM authentication
    _original_cloudauth_init = CloudAuth.__init__

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

    # Custom URL resolver that returns local server URL with /v1 prefix
    def mock_url_resolver(_base_url, _instance, _private_endpoint=False, _region=None) -> str:
        """Always return the local server URL with /v1 prefix."""
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
            token=token,
            instance=instance,
            verify=verify,
            url_resolver=mock_url_resolver,
        )

        yield service


def create_local_service(
    url: str,
    token: str = "test-token",
    instance: str = "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test",
    verify: bool = False,
) -> QiskitRuntimeService:
    """Create QiskitRuntimeService for local server (without context manager).

    WARNING: This function applies monkey-patches globally and permanently.
    Prefer using `local_service_connection()` context manager instead.

    Args:
        url: Local server URL (e.g., "http://localhost:8000")
        token: Mock token (not validated by local server)
        instance: Mock CRN instance identifier
        verify: SSL verification (typically False for localhost)

    Returns:
        QiskitRuntimeService: Configured service instance

    Example:
        >>> service = create_local_service("http://localhost:8000")
        >>> backends = service.backends()
    """
    from qiskit_ibm_runtime.accounts.account import CloudAccount
    from qiskit_ibm_runtime.api.auth import CloudAuth

    # Store original methods
    original_list_instances = CloudAccount.list_instances
    _original_cloudauth_init = CloudAuth.__init__

    # Monkey-patch CloudAccount.list_instances
    def patched_list_instances(self) -> list[dict[str, Any]]:
        """Return mock instance data for local testing."""
        # Check if URL is localhost/127.0.0.1
        if self.url and ("127.0.0.1" in self.url or "localhost" in self.url):
            return [
                {
                    "crn": instance,
                    "plan": "lite",
                    "name": "test-instance",
                }
            ]
        # Otherwise use original implementation
        return original_list_instances(self)

    CloudAccount.list_instances = patched_list_instances

    # Monkey-patch CloudAuth
    def patched_cloudauth_init(
        self, api_key, crn, private=False, proxies=None, verify=True
    ) -> None:
        """Skip IAM setup for localhost testing."""
        self.crn = crn
        self.api_key = api_key
        self.private = private
        self.proxies = proxies
        self.verify = verify
        self.tm = None

    def patched_get_headers(self) -> dict[str, str]:
        """Return simple headers without IAM token."""
        return {
            "Service-CRN": self.crn,
            "Authorization": f"Bearer {self.api_key}",
        }

    CloudAuth.__init__ = patched_cloudauth_init
    CloudAuth.get_headers = patched_get_headers

    # Custom URL resolver
    def mock_url_resolver(_base_url, _instance, _private_endpoint=False, _region=None) -> str:
        """Always return the local server URL with /v1 prefix."""
        return f"{url}/v1"

    # Create service
    service = QiskitRuntimeService(
        channel="ibm_cloud",
        url=url,
        token=token,
        instance=instance,
        verify=verify,
        url_resolver=mock_url_resolver,
    )

    return service


if __name__ == "__main__":
    # Demo usage
    import sys

    from qiskit import QuantumCircuit, transpile
    from qiskit_ibm_runtime import SamplerV2

    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    print(f"Connecting to local server: {server_url}")

    with local_service_connection(server_url) as service:
        # List backends
        backends = service.backends()
        print(f"\nAvailable backends ({len(backends)}):")
        for backend in backends[:5]:  # Show first 5
            print(f"  - {backend.name}")
        if len(backends) > 5:
            print(f"  ... and {len(backends) - 5} more")

        # Run simple circuit
        print("\nRunning Bell state circuit on fake_manila@aer...")
        backend = service.backend("fake_manila@aer")

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure_all()

        # Transpile circuit to backend (required by qiskit-ibm-runtime)
        circuit = transpile(circuit, backend=backend)

        sampler = SamplerV2(mode=backend)
        job = sampler.run([circuit])
        result = job.result()

        print(f"Job ID: {job.job_id()}")
        print(f"Result: {result}")
        print("\nSuccess! ✓")
