"""Aer-based CPU executor implementation."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

    from qiskit.primitives.containers import EstimatorPubLike, SamplerPubLike

from .base import BaseExecutor


class AerExecutor(BaseExecutor):
    """
    CPU-based executor using Qiskit Aer simulator.

    This executor uses AerSimulator with statevector method for fast,
    noise-free quantum circuit simulation on CPU.

    Design notes:
    - No noise model: statevector simulator doesn't support realistic noise
    - No topology constraints: assumes circuits are pre-transpiled by client
    - backend_name parameter is accepted but not used (reserved for future)
    """

    def __init__(
        self,
        shots: int = 1024,
        seed_simulator: int | None = None,
        max_parallel_threads: int = 0,
    ):
        """
        Initialize AerExecutor.

        Args:
            shots: Default number of shots for sampling when not specified in PUB
                   or options. Individual PUBs can override this.
            seed_simulator: Random seed for reproducible results.
            max_parallel_threads: Maximum number of parallel threads (0 = auto).
        """
        self.shots = shots
        self.seed_simulator = seed_simulator
        self.max_parallel_threads = max_parallel_threads

    @property
    def name(self) -> str:
        """Return executor name."""
        return "aer"

    def _create_simulator(self) -> Any:
        """
        Create AerSimulator instance.

        Returns:
            AerSimulator: Configured simulator instance.
        """
        from qiskit_aer import AerSimulator

        options: dict[str, Any] = {
            "method": "statevector",
        }

        if self.seed_simulator is not None:
            options["seed_simulator"] = self.seed_simulator

        if self.max_parallel_threads > 0:
            options["max_parallel_threads"] = self.max_parallel_threads

        simulator = AerSimulator(**options)
        return simulator

    def execute_sampler(
        self,
        pubs: "Iterable[SamplerPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute sampler primitive using Aer simulator.

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
        from qiskit.primitives import BackendSamplerV2

        simulator = self._create_simulator()
        sampler = BackendSamplerV2(backend=simulator)

        # Extract shots from options, fallback to instance default
        shots = options.get("default_shots", self.shots)

        # Run sampler
        job = sampler.run(pubs=pubs, shots=shots)
        result = job.result()

        return result

    def execute_estimator(
        self,
        pubs: "Iterable[EstimatorPubLike]",
        options: dict[str, Any],
        backend_name: str,
    ) -> Any:
        """
        Execute estimator primitive using Aer simulator.

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
        from qiskit.primitives import BackendEstimatorV2

        simulator = self._create_simulator()
        estimator = BackendEstimatorV2(backend=simulator)

        # Extract precision from options if provided
        precision = options.get("default_precision")

        # Run estimator
        if precision is not None:
            job = estimator.run(pubs=pubs, precision=precision)
        else:
            job = estimator.run(pubs=pubs)

        result = job.result()

        return result
