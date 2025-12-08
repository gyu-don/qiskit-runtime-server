"""Integration tests for session management using Qiskit library.

Tests Session (dedicated mode) and Batch (batch mode) using the actual
qiskit-ibm-runtime library as a real user would.
"""

import threading
import time
from collections.abc import Generator

import pytest
import uvicorn
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import SparsePauliOp
from qiskit_ibm_runtime import (
    Batch,
    EstimatorV2,
    QiskitRuntimeService,
    SamplerV2,
    Session,
)

from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor
from tests.conftest import create_test_service


@pytest.fixture(scope="module")
def test_server() -> Generator[str, None, None]:
    """Start a test server in a background thread."""
    app = create_app(
        executors={
            "aer": AerExecutor(
                shots=1024,
                seed_simulator=42,
            )
        }
    )

    host = "127.0.0.1"
    port = 18001

    config = uvicorn.Config(app, host=host, port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for server to start
    import requests

    max_retries = 50
    for _ in range(max_retries):
        try:
            response = requests.get(f"http://{host}:{port}/")
            if response.status_code == 200:
                break
        except requests.ConnectionError:
            time.sleep(0.1)
    else:
        raise RuntimeError("Server failed to start")

    url = f"http://{host}:{port}"
    yield url


@pytest.fixture
def service(test_server: str) -> Generator[QiskitRuntimeService, None, None]:
    """Create QiskitRuntimeService connected to test server."""
    with create_test_service(test_server) as service:
        yield service


@pytest.fixture
def bell_circuit() -> QuantumCircuit:
    """Create a Bell state circuit."""
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


class TestSessionDedicatedMode:
    """Test Session (dedicated mode) - sequential execution."""

    def test_session_single_job(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test running a single job in a session."""
        backend = service.backend("fake_manila@aer")

        # Create session (dedicated mode)
        with Session(backend=backend) as session:
            # Transpile circuit
            isa_circuit = transpile(bell_circuit, backend=backend)

            # Run with SamplerV2
            sampler = SamplerV2(mode=session)
            job = sampler.run([isa_circuit])

            # Wait for result
            result = job.result()

            # Verify result
            assert len(result) == 1
            assert result[0].data.meas.num_shots == 1024

    def test_session_multiple_jobs_sequential(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test running multiple jobs sequentially in a session."""
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            isa_circuit = transpile(bell_circuit, backend=backend)

            # Create multiple jobs
            sampler = SamplerV2(mode=session)
            jobs = []

            for _ in range(3):
                job = sampler.run([isa_circuit])
                jobs.append(job)

            # Wait for all jobs
            for job in jobs:
                result = job.result()
                assert len(result) == 1
                assert result[0].data.meas.num_shots == 1024

    def test_session_close_gracefully(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test that closing a session works correctly."""
        backend = service.backend("fake_manila@aer")

        session = Session(backend=backend)

        # Run a job
        isa_circuit = transpile(bell_circuit, backend=backend)
        sampler = SamplerV2(mode=session)
        job = sampler.run([isa_circuit])

        # Close session
        session.close()

        # Running job should still complete
        result = job.result()
        assert len(result) == 1

    def test_session_with_estimator(self, service: QiskitRuntimeService) -> None:
        """Test estimator primitive in a session."""
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            # Create circuit without measurements
            qc = QuantumCircuit(2)
            qc.h(0)
            qc.cx(0, 1)

            isa_circuit = transpile(qc, backend=backend)

            # Create observable matching transpiled circuit size
            num_qubits = isa_circuit.num_qubits
            observable = SparsePauliOp("Z" * num_qubits)

            # Run estimator
            estimator = EstimatorV2(mode=session)
            job = estimator.run([(isa_circuit, observable)])

            result = job.result()
            assert len(result) == 1
            assert hasattr(result[0].data, "evs")


class TestBatchMode:
    """Test Batch mode - parallel execution."""

    def test_batch_multiple_jobs(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test running multiple jobs in batch mode."""
        backend = service.backend("fake_manila@aer")

        # Create batch
        with Batch(backend=backend) as batch:
            isa_circuit = transpile(bell_circuit, backend=backend)

            # Submit multiple jobs
            sampler = SamplerV2(mode=batch)
            jobs = []

            for _ in range(3):
                job = sampler.run([isa_circuit])
                jobs.append(job)

            # All jobs should complete
            for job in jobs:
                result = job.result()
                assert len(result) == 1
                assert result[0].data.meas.num_shots == 1024

    def test_batch_with_estimator(self, service: QiskitRuntimeService) -> None:
        """Test estimator in batch mode."""
        backend = service.backend("fake_manila@aer")

        with Batch(backend=backend) as batch:
            qc = QuantumCircuit(2)
            qc.h(0)
            qc.cx(0, 1)

            isa_circuit = transpile(qc, backend=backend)

            # Create observable matching transpiled circuit size
            num_qubits = isa_circuit.num_qubits
            observable = SparsePauliOp("Z" * num_qubits)

            estimator = EstimatorV2(mode=batch)
            job = estimator.run([(isa_circuit, observable)])

            result = job.result()
            assert len(result) == 1


class TestSessionValidation:
    """Test session validation and error handling."""

    def test_session_backend_specified(self, service: QiskitRuntimeService) -> None:
        """Test that session requires a backend."""
        backend = service.backend("fake_manila@aer")

        # Should work with backend
        with Session(backend=backend):
            pass  # Session created successfully

    def test_different_circuits_same_session(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test running different circuits in the same session."""
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            sampler = SamplerV2(mode=session)

            # Circuit 1: Bell state
            isa_circuit1 = transpile(bell_circuit, backend=backend)
            job1 = sampler.run([isa_circuit1])

            # Circuit 2: Different circuit
            qc2 = QuantumCircuit(2)
            qc2.x(0)
            qc2.x(1)
            qc2.measure_all()
            isa_circuit2 = transpile(qc2, backend=backend)
            job2 = sampler.run([isa_circuit2])

            # Both should complete
            result1 = job1.result()
            result2 = job2.result()

            assert len(result1) == 1
            assert len(result2) == 1


class TestSessionLifecycle:
    """Test session lifecycle management."""

    def test_session_context_manager(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test session with context manager."""
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            isa_circuit = transpile(bell_circuit, backend=backend)
            sampler = SamplerV2(mode=session)
            job = sampler.run([isa_circuit])
            result = job.result()
            assert len(result) == 1

        # Session should be closed after context

    def test_batch_context_manager(
        self, service: QiskitRuntimeService, bell_circuit: QuantumCircuit
    ) -> None:
        """Test batch with context manager."""
        backend = service.backend("fake_manila@aer")

        with Batch(backend=backend) as batch:
            isa_circuit = transpile(bell_circuit, backend=backend)
            sampler = SamplerV2(mode=batch)
            job = sampler.run([isa_circuit])
            result = job.result()
            assert len(result) == 1

        # Batch should be closed after context


class TestMixedPrimitives:
    """Test mixing sampler and estimator in sessions."""

    def test_session_sampler_and_estimator(self, service: QiskitRuntimeService) -> None:
        """Test using both sampler and estimator in same session."""
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            # Sampler job
            qc_sampler = QuantumCircuit(2)
            qc_sampler.h(0)
            qc_sampler.cx(0, 1)
            qc_sampler.measure_all()
            isa_sampler = transpile(qc_sampler, backend=backend)

            sampler = SamplerV2(mode=session)
            sampler_job = sampler.run([isa_sampler])

            # Estimator job
            qc_estimator = QuantumCircuit(2)
            qc_estimator.h(0)
            qc_estimator.cx(0, 1)
            isa_estimator = transpile(qc_estimator, backend=backend)

            # Create observable matching transpiled circuit size
            num_qubits = isa_estimator.num_qubits
            observable = SparsePauliOp("Z" * num_qubits)

            estimator = EstimatorV2(mode=session)
            estimator_job = estimator.run([(isa_estimator, observable)])

            # Both should complete
            sampler_result = sampler_job.result()
            estimator_result = estimator_job.result()

            assert len(sampler_result) == 1
            assert len(estimator_result) == 1


class TestBackendSelection:
    """Test backend selection in sessions."""

    def test_session_with_explicit_executor(self, service: QiskitRuntimeService) -> None:
        """Test session with explicitly named executor."""
        # Use @aer executor explicitly
        backend = service.backend("fake_manila@aer")

        with Session(backend=backend) as session:
            qc = QuantumCircuit(2)
            qc.h(0)
            qc.cx(0, 1)
            qc.measure_all()

            isa_circuit = transpile(qc, backend=backend)
            sampler = SamplerV2(mode=session)
            job = sampler.run([isa_circuit])

            result = job.result()
            assert len(result) == 1
