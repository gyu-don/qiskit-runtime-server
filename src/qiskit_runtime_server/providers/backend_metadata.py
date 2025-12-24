"""Backend metadata provider using FakeProviderForBackendV2."""

from typing import Any

from qiskit.providers.fake_provider import GenericBackendV2
from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

from ..models import BackendsResponse

# Statevector backend names (reserved names for ideal simulators)
STATEVECTOR_BACKEND_NAMES = [
    "statevector_simulator",
]


class BackendMetadataProvider:
    """
    Provider for backend metadata from multiple sources.

    Supports:
    - FakeProviderForBackendV2 (59 real hardware topologies)
    - GenericBackendV2 (statevector simulators)
    - Parsing 'metadata@executor' backend names
    - Listing virtual backends (metadata x executor combinations)
    """

    def __init__(
        self,
        available_executors: list[str],
        statevector_config: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize the backend metadata provider.

        Args:
            available_executors: List of executor names (e.g., ["aer", "custatevec"]).
            statevector_config: Optional configuration for statevector backend.
                               Defaults to {"num_qubits": 30, "enabled": True}.
        """
        self.available_executors = available_executors
        self.provider = FakeProviderForBackendV2()

        # Statevector backend configuration
        if statevector_config is None:
            statevector_config = {"num_qubits": 30, "enabled": True}
        self.statevector_config = statevector_config

        # Create statevector backend if enabled
        if self.statevector_config.get("enabled", True):
            self._statevector_backend = self._create_statevector_backend()
        else:
            self._statevector_backend = None

    def _create_statevector_backend(self) -> GenericBackendV2:
        """Create statevector backend metadata."""
        return GenericBackendV2(
            num_qubits=self.statevector_config.get("num_qubits", 30),
            basis_gates=[
                "cx",
                "id",
                "rz",
                "sx",
                "x",
                "h",
                "y",
                "z",
                "s",
                "sdg",
                "t",
                "tdg",
                "swap",
                "reset",
                "delay",
                "measure",
            ],
            coupling_map=None,  # Fully connected (no topology constraints)
        )

    def _is_statevector_backend(self, metadata_name: str) -> bool:
        """Check if backend name is a statevector backend."""
        return (
            self._statevector_backend is not None
            and metadata_name in STATEVECTOR_BACKEND_NAMES
        )

    def _backend_exists(self, metadata_name: str) -> bool:
        """Check if a backend with the given metadata name exists."""
        # Check statevector backends
        if self._is_statevector_backend(metadata_name):
            return True

        # Check FakeProvider backends
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

    def get_backend(self, metadata_name: str) -> Any:
        """
        Get backend object by metadata name.

        Args:
            metadata_name: Backend metadata name (without executor suffix).

        Returns:
            Backend object (GenericBackendV2 or FakeProvider backend).

        Raises:
            ValueError: If backend does not exist.

        Examples:
            >>> provider = BackendMetadataProvider(["aer"])
            >>> backend = provider.get_backend("fake_manila")
            >>> backend.name
            'fake_manila'
            >>> backend = provider.get_backend("statevector_simulator")
            >>> backend.name
            'statevector_simulator'
        """
        if self._is_statevector_backend(metadata_name):
            # Return statevector backend with custom name
            backend = self._statevector_backend
            if backend is not None:
                # Create a copy to avoid modifying the original
                # Note: GenericBackendV2 doesn't have a good copy mechanism,
                # so we'll just set the name directly (it's a simple attribute)
                backend._name = metadata_name
                return backend
            raise ValueError(f"Statevector backend '{metadata_name}' is not available")
        else:
            # Return FakeProvider backend
            return self.provider.backend(metadata_name)

    def _backend_to_dict(self, backend: Any) -> dict[str, Any]:
        """
        Convert a backend object to a dictionary representation.

        Args:
            backend: Backend object (FakeProvider or GenericBackendV2).

        Returns:
            Dictionary with backend metadata.
        """
        # Check if backend has to_dict method (FakeProvider backends)
        if hasattr(backend, "to_dict") and callable(backend.to_dict):
            result: dict[str, Any] = backend.to_dict()
        else:
            # GenericBackendV2 doesn't have to_dict, build manually
            result = {
                "backend_name": backend.name,
                "name": backend.name,
                "backend_version": getattr(backend, "backend_version", "2"),
                "n_qubits": backend.num_qubits,
                "simulator": True,
                "local": True,
                "conditional": True,
                "memory": True,
                "open_pulse": False,
                "max_shots": getattr(backend, "max_shots", 1000000),
                "coupling_map": None,  # Statevector backends are fully connected
                "description": getattr(backend, "description", ""),
            }

            # Add basis gates
            if hasattr(backend, "operation_names"):
                result["supported_instructions"] = list(backend.operation_names)

        # Ensure operational status (server-side property, not in backend metadata)
        result["operational"] = True

        # max_experiments is a server-side limit, not in backend metadata
        if "max_experiments" not in result:
            result["max_experiments"] = 300

        # Add supported_instructions if not present
        if "supported_instructions" not in result and hasattr(backend, "operation_names"):
            result["supported_instructions"] = list(backend.operation_names)

        return result

    def list_backends(self, fields: str | None = None) -> BackendsResponse:
        """
        Generate all virtual backends:
        - FakeProvider backends × executors
        - Statevector backends × executors

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
            >>> "statevector_simulator@aer" in backend_names
            True
        """
        virtual_backends = []

        # 1. Add FakeProvider backends
        base_backends = self.provider.backends()
        for backend in base_backends:
            for executor_name in self.available_executors:
                virtual_name = f"{backend.name}@{executor_name}"
                backend_dict = self._backend_to_dict(backend)
                backend_dict["name"] = virtual_name
                backend_dict["backend_name"] = virtual_name
                virtual_backends.append(backend_dict)

        # 2. Add Statevector backends (if enabled)
        if self._statevector_backend is not None:
            for statevector_name in STATEVECTOR_BACKEND_NAMES:
                backend = self.get_backend(statevector_name)
                for executor_name in self.available_executors:
                    virtual_name = f"{statevector_name}@{executor_name}"
                    backend_dict = self._backend_to_dict(backend)
                    backend_dict["name"] = virtual_name
                    backend_dict["backend_name"] = virtual_name
                    # Override description to clarify it's a statevector simulator
                    backend_dict["description"] = (
                        f"Statevector simulator (ideal, no noise) on {executor_name} executor"
                    )
                    virtual_backends.append(backend_dict)

        return BackendsResponse(devices=virtual_backends)


# Global singleton instance
_provider_instance: BackendMetadataProvider | None = None


def get_backend_metadata_provider(
    available_executors: list[str] | None = None,
    statevector_config: dict[str, Any] | None = None,
) -> BackendMetadataProvider:
    """
    Get or create the global BackendMetadataProvider singleton.

    Args:
        available_executors: List of executor names. Defaults to ["aer"].
                            Only used on first call.
        statevector_config: Optional configuration for statevector backend.
                           Defaults to {"num_qubits": 30, "enabled": True}.
                           Only used on first call.

    Returns:
        BackendMetadataProvider: The global provider instance.
    """
    global _provider_instance

    if _provider_instance is None:
        if available_executors is None:
            available_executors = ["aer"]
        _provider_instance = BackendMetadataProvider(
            available_executors, statevector_config
        )

    return _provider_instance


def reset_backend_metadata_provider() -> None:
    """Reset the global provider instance (for testing)."""
    global _provider_instance
    _provider_instance = None
