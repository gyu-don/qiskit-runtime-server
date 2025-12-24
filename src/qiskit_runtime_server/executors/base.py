"""Base executor interface for circuit execution backends."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qiskit.primitives.containers import EstimatorPubLike, SamplerPubLike

from ..providers.backend_metadata import get_backend_metadata_provider


class BaseExecutor(ABC):
    """
    Abstract base class for executor implementations.

    Executors handle the actual quantum circuit execution using different
    simulation backends (CPU, GPU, etc.).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the executor name.

        Returns:
            str: Executor identifier (e.g., "aer", "custatevec")
        """
        pass

    @abstractmethod
    def execute_sampler(
        self,
        pubs: "Iterable[SamplerPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute sampler primitive.

        Args:
            pubs: Iterable of primitive unified blocs (PUBs) containing circuits,
                  parameter values, and shots. Each PUB can be:
                  - QuantumCircuit
                  - (circuit,)
                  - (circuit, parameter_values)
                  - (circuit, parameter_values, shots)
            options: Execution options (e.g., default_shots, seed).
            backend_name: Backend metadata name (e.g., "fake_manila").
                         Currently not used but reserved for future extensions.

        Returns:
            PrimitiveResult: Sampler execution result.
        """
        pass

    @abstractmethod
    def execute_estimator(
        self,
        pubs: "Iterable[EstimatorPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute estimator primitive.

        Args:
            pubs: Iterable of primitive unified blocs (PUBs) containing circuits,
                  observables, parameter values, and precision. Each PUB can be:
                  - (circuit, observables)
                  - (circuit, observables, parameter_values)
                  - (circuit, observables, parameter_values, precision)
            options: Execution options (e.g., default_precision, seed).
            backend_name: Backend metadata name (e.g., "fake_manila").
                         Currently not used but reserved for future extensions.

        Returns:
            PrimitiveResult: Estimator execution result.
        """
        pass

    def get_backend_metadata_provider(self) -> Any:
        """
        Get the backend metadata provider singleton.

        This helper provides access to backend topology and calibration data
        from FakeProviderForBackendV2.

        Returns:
            BackendMetadataProvider: The global metadata provider instance.
        """
        return get_backend_metadata_provider()

    def get_backend(self, backend_name: str) -> Any:
        """
        Get backend object by metadata name.

        This helper allows executors to access backend metadata (topology,
        calibration data) for noise modeling or validation.

        Args:
            backend_name: Backend metadata name (without executor suffix).
                         Examples: "fake_manila", "statevector_simulator"

        Returns:
            Backend object (GenericBackendV2 or FakeProvider backend).

        Raises:
            ValueError: If backend does not exist.

        Examples:
            >>> executor = AerExecutor()
            >>> backend = executor.get_backend("fake_manila")
            >>> backend.num_qubits
            5
            >>> backend = executor.get_backend("statevector_simulator")
            >>> backend.num_qubits
            30
        """
        provider = self.get_backend_metadata_provider()
        return provider.get_backend(backend_name)
