"""GPU-accelerated executor using NVIDIA cuStateVec.

This executor uses Qiskit Aer's StatevectorSimulator with cuStateVec backend for
GPU-accelerated statevector simulation. Requires CUDA-compatible GPU and
cuQuantum installation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from qiskit.primitives import BackendEstimatorV2, BackendSamplerV2

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qiskit.primitives.containers import EstimatorPubLike, SamplerPubLike

from .base import BaseExecutor

# Check if cuQuantum is available
try:
    from cusvaer.backends import StatevectorSimulator  # type: ignore[import-not-found]

    CUSTATEVEC_AVAILABLE = True
except ImportError:
    CUSTATEVEC_AVAILABLE = False


class CuStateVecExecutor(BaseExecutor):
    """
    GPU-accelerated executor using NVIDIA cuStateVec through Qiskit Aer.

    This executor uses StatevectorSimulator with GPU device and cuStateVec enabled for
    high-performance statevector simulation on NVIDIA GPUs.

    Design notes:
    - Uses cusvaer StatevectorSimulator
    - Requires CUDA-compatible NVIDIA GPU
    - Requires cusvaer package (cuQuantum Appliance)
    - No noise model: statevector simulator doesn't support realistic noise
    - No topology constraints: assumes circuits are pre-transpiled by client
    - backend_name parameter is accepted but not used (reserved for future)
    """

    def __init__(
        self,
        device_id: int = 0,
        shots: int = 1024,
        seed_simulator: int | None = None,
        max_parallel_threads: int = 0,
    ):
        """
        Initialize CuStateVecExecutor.

        Args:
            device_id: CUDA device ID to use (default: 0).
            shots: Default number of shots for sampling when not specified in PUB
                   or options. Individual PUBs can override this.
            seed_simulator: Random seed for reproducible results.
            max_parallel_threads: Maximum number of parallel threads (0 = auto).

        Raises:
            ImportError: If cuQuantum is not installed.
        """
        if not CUSTATEVEC_AVAILABLE:
            raise ImportError(
                "cuQuantum is not installed. Install with: pip install cuquantum-python"
            )

        self.device_id = device_id
        self.shots = shots
        self.seed_simulator = seed_simulator
        self.max_parallel_threads = max_parallel_threads

    @property
    def name(self) -> str:
        """Return executor name."""
        return "custatevec"

    def _create_simulator(self) -> StatevectorSimulator:
        """
        Create StatevectorSimulator instance with GPU device.

        Returns:
            StatevectorSimulator: Configured GPU simulator instance.
        """
        options: dict[str, Any] = {}

        if self.seed_simulator is not None:
            options["seed_simulator"] = self.seed_simulator

        if self.max_parallel_threads > 0:
            options["max_parallel_threads"] = self.max_parallel_threads

        # Set CUDA device ID if specified
        if self.device_id > 0:
            options["device_id"] = self.device_id

        simulator = StatevectorSimulator(**options)
        return simulator

    def execute_sampler(
        self,
        pubs: Iterable[SamplerPubLike],
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute sampler primitive using GPU-accelerated StatevectorSimulator with cuStateVec.

        Args:
            pubs: List of primitive unified blocs (PUBs). Each PUB can be:
                  - QuantumCircuit
                  - (circuit,)
                  - (circuit, parameter_values)
                  - (circuit, parameter_values, shots)
            options: Execution options. "default_shots" applies to PUBs without
                     explicit shots. If not provided, uses self.shots.
            backend_name: Backend metadata name (currently unused).

        Returns:
            PrimitiveResult: Sampler execution result.
        """
        simulator = self._create_simulator()
        sampler = BackendSamplerV2(backend=simulator)

        # Extract shots from options, fallback to instance default
        shots = options.get("default_shots", self.shots)

        # Run sampler on GPU
        job = sampler.run(pubs=pubs, shots=shots)
        result = job.result()

        return result

    def execute_estimator(
        self,
        pubs: Iterable[EstimatorPubLike],
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute estimator primitive using GPU-accelerated StatevectorSimulator with cuStateVec.

        Args:
            pubs: Iterable of primitive unified blocs (PUBs). Each PUB can be:
                  - (circuit, observables)
                  - (circuit, observables, parameter_values)
                  - (circuit, observables, parameter_values, precision)
            options: Execution options (e.g., default_precision).
            backend_name: Backend metadata name (currently unused).

        Returns:
            PrimitiveResult: Estimator execution result.
        """
        simulator = self._create_simulator()
        estimator = BackendEstimatorV2(backend=simulator)

        # Extract precision from options if provided
        precision = options.get("default_precision")

        # Run estimator on GPU
        if precision is not None:
            job = estimator.run(pubs=pubs, precision=precision)
        else:
            job = estimator.run(pubs=pubs)

        result = job.result()

        return result
