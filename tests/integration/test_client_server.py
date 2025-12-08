"""End-to-end integration tests using QiskitRuntimeService with real HTTP server.

These tests verify the full stack:
1. Server runs on actual HTTP port
2. QiskitRuntimeService connects to the server via HTTP
3. Full client-server interaction (backends, jobs, results)

NOTE: We use create_test_service from conftest to avoid IBM Cloud dependencies.
This allows testing with a local server while using the actual client library.
"""

import threading
import time
from collections.abc import Generator

import pytest
import uvicorn
from qiskit import QuantumCircuit
from qiskit.providers.exceptions import QiskitBackendNotFoundError
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor
from tests.conftest import create_test_service


@pytest.fixture(scope="module")
def test_server() -> Generator[str, None, None]:
    """Start a test server in a background thread.

    Yields the server URL for HTTP client connection.
    """
    # Create app with test executors
    app = create_app(
        executors={
            "aer": AerExecutor(
                shots=1024,
                seed_simulator=42,  # Deterministic for testing
            )
        }
    )

    # Server configuration
    host = "127.0.0.1"
    port = 18000  # Use non-standard port to avoid conflicts

    # Run server in background thread
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

    # Server will shut down when test process exits (daemon thread)


@pytest.fixture
def service(test_server: str) -> Generator[QiskitRuntimeService, None, None]:
    """Create QiskitRuntimeService connected to test server.

    Uses create_test_service helper from conftest to patch authentication.
    """
    with create_test_service(test_server) as service:
        yield service


class TestEndToEndBackends:
    """Test backend listing and information retrieval via QiskitRuntimeService."""

    def test_list_backends(self, service: QiskitRuntimeService) -> None:
        """Test listing backends returns virtual backends."""
        backends = service.backends()
        backend_names = [b.name for b in backends]

        # Should have virtual backends with @aer suffix
        assert "fake_manila@aer" in backend_names
        assert "fake_athens@aer" in backend_names
        assert len(backend_names) > 0

    def test_get_backend_info(self, service: QiskitRuntimeService) -> None:
        """Test retrieving specific backend information."""
        backend = service.backend("fake_manila@aer")

        # Verify backend properties
        assert backend.name == "fake_manila@aer"
        assert backend.num_qubits == 5
        # coupling_map may be None for IBMBackend, check target instead
        assert backend.target is not None
        assert backend.target.num_qubits == 5
        assert len(backend.operation_names) > 0  # basis_gates


class TestEndToEndSampler:
    """Test Sampler execution end-to-end via QiskitRuntimeService."""

    def test_simple_bell_circuit(self, service: QiskitRuntimeService) -> None:
        """Test running a simple Bell state circuit with Sampler."""
        from qiskit import transpile

        # Get backend
        backend = service.backend("fake_manila@aer")

        # Create Bell state circuit
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure_all()

        # Transpile circuit to backend (required by qiskit-ibm-runtime)
        circuit = transpile(circuit, backend=backend)

        # Run with SamplerV2
        sampler = SamplerV2(mode=backend)
        job = sampler.run([circuit])

        # Verify job was created
        assert job.job_id() is not None

        # Wait for result (with timeout)
        result = job.result()

        # Verify result structure
        assert result is not None
        assert len(result) == 1

        # Verify measurement outcomes
        pub_result = result[0]
        assert pub_result.data is not None

        # Bell state should have outcomes
        counts = pub_result.data.meas.get_counts()
        assert len(counts) > 0
        # Bell state typically has |00> and |11>
        assert any(key in counts for key in ["00", "11"])

    def test_multiple_circuits(self, service: QiskitRuntimeService) -> None:
        """Test running multiple circuits in one job."""
        from qiskit import transpile

        backend = service.backend("fake_manila@aer")

        # Create two different circuits
        circuit1 = QuantumCircuit(1)
        circuit1.h(0)
        circuit1.measure_all()

        circuit2 = QuantumCircuit(2)
        circuit2.h(0)
        circuit2.cx(0, 1)
        circuit2.measure_all()

        # Transpile circuits to backend
        circuit1 = transpile(circuit1, backend=backend)
        circuit2 = transpile(circuit2, backend=backend)

        # Run both circuits
        sampler = SamplerV2(mode=backend)
        job = sampler.run([circuit1, circuit2])
        result = job.result()

        # Should get results for both circuits
        assert len(result) == 2
        assert result[0].data is not None
        assert result[1].data is not None


class TestEndToEndJobLifecycle:
    """Test job lifecycle and status transitions via QiskitRuntimeService."""

    def test_job_status_progression(self, service: QiskitRuntimeService) -> None:
        """Test job status progresses through states."""
        from qiskit import transpile

        backend = service.backend("fake_manila@aer")

        # Create a simple circuit
        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        # Transpile circuit to backend
        circuit = transpile(circuit, backend=backend)

        # Submit job
        sampler = SamplerV2(mode=backend)
        job = sampler.run([circuit])

        # Job should have valid ID
        job_id = job.job_id()
        assert job_id is not None
        assert job_id.startswith("job-")

        # Check status (may be QUEUED, RUNNING, or already DONE)
        # Note: qiskit-ibm-runtime client maps COMPLETED -> DONE
        status = job.status()
        assert status in ["QUEUED", "RUNNING", "DONE"]

        # Wait for completion
        result = job.result()
        assert result is not None

        # Final status should be DONE (client maps COMPLETED -> DONE)
        final_status = job.status()
        assert final_status == "DONE"


class TestEndToEndErrorHandling:
    """Test error handling in QiskitRuntimeService interaction."""

    def test_invalid_backend(self, service: QiskitRuntimeService) -> None:
        """Test requesting a non-existent backend."""
        with pytest.raises(QiskitBackendNotFoundError):
            service.backend("nonexistent_backend@aer")

    def test_backend_without_executor(self, service: QiskitRuntimeService) -> None:
        """Test that only configured executors appear in backend list."""
        backends = service.backends()
        backend_names = [b.name for b in backends]

        # Server only has 'aer' executor, not 'gpu'
        gpu_backends = [name for name in backend_names if "@gpu" in name]
        assert len(gpu_backends) == 0

        # All backends should have @aer suffix
        for name in backend_names:
            assert "@aer" in name
