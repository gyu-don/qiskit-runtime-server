"""GPU-accelerated executor using NVIDIA cuStateVec.

This executor uses cuQuantum's cuStateVec library for GPU-accelerated
statevector simulation. Requires CUDA-compatible GPU and cuQuantum installation.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qiskit.primitives.containers import EstimatorPubLike, SamplerPubLike

from .base import BaseExecutor

# Check if cuQuantum is available
try:
    from cuquantum import custatevec  # noqa: F401

    CUSTATEVEC_AVAILABLE = True
except ImportError:
    CUSTATEVEC_AVAILABLE = False


class CuStateVecExecutor(BaseExecutor):
    """
    GPU-accelerated executor using NVIDIA cuStateVec.

    This executor leverages cuQuantum's cuStateVec library for high-performance
    statevector simulation on NVIDIA GPUs.

    Note:
        - Requires CUDA-compatible NVIDIA GPU
        - Requires cuQuantum Python package (cuquantum-python)
        - Does not use noise models (statevector simulation)
        - Does not reference backend topology (client handles transpilation)
    """

    def __init__(
        self,
        device_id: int = 0,
        shots: int = 1024,
        seed_simulator: int | None = None,
    ):
        """
        Initialize the GPU executor.

        Args:
            device_id: CUDA device ID to use (default: 0).
            shots: Default number of shots for sampling (default: 1024).
            seed_simulator: Random seed for reproducibility (default: None).

        Raises:
            ImportError: If cuQuantum is not installed.
            RuntimeError: If no compatible GPU is found.
        """
        if not CUSTATEVEC_AVAILABLE:
            raise ImportError(
                "cuQuantum is not installed. Install with: pip install cuquantum-python"
            )

        self.device_id = device_id
        self.shots = shots
        self.seed_simulator = seed_simulator

        # Verify GPU availability (stub - not implemented)
        self._verify_gpu()

    def _verify_gpu(self) -> None:
        """
        Verify that a compatible GPU is available.

        Raises:
            RuntimeError: If no compatible GPU is found.
        """
        # TODO: Implement GPU verification
        # - Check CUDA availability
        # - Check GPU device count
        # - Verify device_id is valid
        # - Check cuQuantum compatibility
        pass

    @property
    def name(self) -> str:
        """Return the executor name."""
        return "custatevec"

    def execute_sampler(
        self,
        pubs: "Iterable[SamplerPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute sampler primitive using GPU.

        Args:
            pubs: Iterable of primitive unified blocs (PUBs).
            options: Execution options (e.g., default_shots, seed).
            backend_name: Backend metadata name (reserved for future use).

        Returns:
            PrimitiveResult: Sampler execution result.

        Raises:
            NotImplementedError: This is a stub implementation.
        """
        # TODO: Implement GPU sampler execution
        # - Convert circuits to GPU-compatible format
        # - Execute on GPU using cuStateVec
        # - Sample measurement outcomes
        # - Return PrimitiveResult
        raise NotImplementedError("CuStateVecExecutor.execute_sampler is not implemented yet")

    def execute_estimator(
        self,
        pubs: "Iterable[EstimatorPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute estimator primitive using GPU.

        Args:
            pubs: Iterable of primitive unified blocs (PUBs).
            options: Execution options (e.g., default_precision, seed).
            backend_name: Backend metadata name (reserved for future use).

        Returns:
            PrimitiveResult: Estimator execution result.

        Raises:
            NotImplementedError: This is a stub implementation.
        """
        # TODO: Implement GPU estimator execution
        # - Convert circuits and observables to GPU format
        # - Execute on GPU using cuStateVec
        # - Compute expectation values
        # - Return PrimitiveResult
        raise NotImplementedError("CuStateVecExecutor.execute_estimator is not implemented yet")
