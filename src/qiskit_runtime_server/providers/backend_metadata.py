"""Backend metadata provider using FakeProviderForBackendV2."""

from typing import Any

from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

from ..models import BackendsResponse


class BackendMetadataProvider:
    """
    Provider for backend metadata from FakeProviderForBackendV2.

    Supports:
    - Parsing 'metadata@executor' backend names
    - Listing virtual backends (metadata x executor combinations)
    """

    def __init__(self, available_executors: list[str]) -> None:
        """
        Initialize the backend metadata provider.

        Args:
            available_executors: List of executor names (e.g., ["aer", "custatevec"]).
        """
        self.available_executors = available_executors
        self.provider = FakeProviderForBackendV2()

    def _backend_exists(self, metadata_name: str) -> bool:
        """Check if a backend with the given metadata name exists."""
        try:
            self.provider.backend(metadata_name)
            return True
        except Exception:
            return False

    def parse_backend_name(self, backend_name: str) -> tuple[str, str] | None:
        """
        Parse 'metadata@executor' format backend name.

        Args:
            backend_name: Backend name in format 'metadata@executor'.

        Returns:
            Tuple of (metadata_name, executor_name) if valid, None otherwise.

        Examples:
            >>> provider = BackendMetadataProvider(["aer"])
            >>> provider.parse_backend_name("fake_manila@aer")
            ("fake_manila", "aer")
            >>> provider.parse_backend_name("fake_manila")
            None
            >>> provider.parse_backend_name("fake_manila@unknown")
            None
        """
        if "@" not in backend_name:
            return None

        metadata_name, executor_name = backend_name.split("@", 1)

        if executor_name not in self.available_executors:
            return None

        if not self._backend_exists(metadata_name):
            return None

        return (metadata_name, executor_name)

    def _backend_to_dict(self, backend: Any) -> dict[str, Any]:
        """
        Convert a backend object to a dictionary representation.

        Args:
            backend: Backend object from FakeProviderForBackendV2.

        Returns:
            Dictionary with backend metadata.
        """
        # Get basic properties
        result: dict[str, Any] = {
            "backend_name": backend.name,
            "backend_version": getattr(backend, "backend_version", "2"),
            "num_qubits": backend.num_qubits,
            "simulator": False,  # Fake backends represent real devices
            "online_date": None,
            "operational": True,
        }

        # Add coupling map if available
        if hasattr(backend, "coupling_map") and backend.coupling_map is not None:
            result["coupling_map"] = list(backend.coupling_map.get_edges())

        # Add basis gates
        if hasattr(backend, "operation_names"):
            result["basis_gates"] = list(backend.operation_names)

        return result

    def list_backends(self, fields: str | None = None) -> BackendsResponse:
        """
        Generate all metadata × executor combinations as virtual backends.

        Args:
            fields: Optional field filter (not yet implemented).

        Returns:
            BackendsResponse with virtual backend list.

        Examples:
            >>> provider = BackendMetadataProvider(["aer", "custatevec"])
            >>> response = provider.list_backends()
            >>> backend_names = [b["backend_name"] for b in response.devices]
            >>> "fake_manila@aer" in backend_names
            True
            >>> "fake_manila@custatevec" in backend_names
            True
        """
        base_backends = self.provider.backends()
        virtual_backends = []

        for backend in base_backends:
            for executor_name in self.available_executors:
                virtual_name = f"{backend.name}@{executor_name}"
                backend_dict = self._backend_to_dict(backend)
                backend_dict["backend_name"] = virtual_name
                virtual_backends.append(backend_dict)

        return BackendsResponse(devices=virtual_backends)


# Global singleton instance
_provider_instance: BackendMetadataProvider | None = None


def get_backend_metadata_provider(
    available_executors: list[str] | None = None,
) -> BackendMetadataProvider:
    """
    Get or create the global BackendMetadataProvider singleton.

    Args:
        available_executors: List of executor names. Defaults to ["aer"].
                            Only used on first call.

    Returns:
        BackendMetadataProvider: The global provider instance.
    """
    global _provider_instance

    if _provider_instance is None:
        if available_executors is None:
            available_executors = ["aer"]
        _provider_instance = BackendMetadataProvider(available_executors)

    return _provider_instance


def reset_backend_metadata_provider() -> None:
    """Reset the global provider instance (for testing)."""
    global _provider_instance
    _provider_instance = None
