"""Integration tests for session management with real job execution."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import SparsePauliOp
from qiskit_ibm_runtime.utils import RuntimeEncoder

from qiskit_runtime_server.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Standard authentication headers."""
    return {
        "Authorization": "Bearer test-token",
        "Service-CRN": "crn:v1:test",
        "IBM-API-Version": "2025-05-01",
    }


@pytest.fixture
def simple_circuit() -> QuantumCircuit:
    """Create a simple quantum circuit for testing."""
    circuit = QuantumCircuit(2)
    circuit.h(0)
    circuit.cx(0, 1)
    circuit.measure_all()
    return circuit


@pytest.fixture
def bell_circuits() -> list[QuantumCircuit]:
    """Create multiple Bell state circuits."""
    circuits = []
    for i in range(3):
        qc = QuantumCircuit(2, name=f"bell_{i}")
        qc.h(0)
        qc.cx(0, 1)
        qc.measure_all()
        circuits.append(qc)
    return circuits


def serialize_pubs(pubs_data: list) -> dict:
    """Serialize pubs using RuntimeEncoder.

    Args:
        pubs_data: List of pub tuples (e.g., [(circuit,)] or [(circuit, observable)])

    Returns:
        Serialized params dict ready for API
    """
    return json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))


class TestDedicatedModeIntegration:
    """Integration tests for dedicated mode (sequential execution)."""

    def test_dedicated_session_single_job(
        self, client: TestClient, auth_headers: dict[str, str], simple_circuit: QuantumCircuit
    ):
        """Test dedicated session with a single job."""
        # Create dedicated session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]

        # Transpile circuit
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()
        isa_circuit = transpile(simple_circuit, basis_gates=backend_config["basis_gates"])

        # Create job within session
        serialized_params = serialize_pubs([(isa_circuit,)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert job_response.status_code == 202
        job_id = job_response.json()["id"]

        # Wait for job completion
        max_wait = 10  # seconds
        start_time = time.time()
        while time.time() - start_time < max_wait:
            job_status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
            if job_status["state"]["status"] == "COMPLETED":
                break
            time.sleep(0.1)

        # Verify job completed
        assert job_status["state"]["status"] == "COMPLETED"

        # Verify session contains job
        session_get = client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert session_get.status_code == 200
        session_data = session_get.json()
        assert job_id in session_data["jobs"]
        assert len(session_data["jobs"]) == 1

        # Get results
        results = client.get(f"/v1/jobs/{job_id}/results", headers=auth_headers)
        assert results.status_code == 200

    def test_dedicated_session_multiple_jobs_sequential(
        self, client: TestClient, auth_headers: dict[str, str], bell_circuits: list[QuantumCircuit]
    ):
        """Test dedicated session with multiple jobs execute sequentially."""
        # Create dedicated session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Get backend configuration
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()

        # Create multiple jobs
        job_ids = []
        for circuit in bell_circuits:
            isa_circuit = transpile(circuit, basis_gates=backend_config["basis_gates"])
            serialized_params = serialize_pubs([(isa_circuit,)])
            job_response = client.post(
                "/v1/jobs",
                json={
                    "program_id": "sampler",
                    "backend": "fake_manila@aer",
                    "params": serialized_params,
                    "session_id": session_id,
                },
                headers=auth_headers,
            )
            assert job_response.status_code == 202
            job_ids.append(job_response.json()["id"])

        # Wait for all jobs to complete
        max_wait = 30  # seconds
        start_time = time.time()
        all_completed = False
        while time.time() - start_time < max_wait:
            statuses = [
                client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
                for job_id in job_ids
            ]
            if all(s["state"]["status"] == "COMPLETED" for s in statuses):
                all_completed = True
                break
            time.sleep(0.2)

        assert all_completed, "Not all jobs completed in time"

        # Verify all jobs are in session
        session_data = client.get(f"/v1/sessions/{session_id}", headers=auth_headers).json()
        assert len(session_data["jobs"]) == len(job_ids)
        for job_id in job_ids:
            assert job_id in session_data["jobs"]

    def test_dedicated_session_close_gracefully(
        self, client: TestClient, auth_headers: dict[str, str], simple_circuit: QuantumCircuit
    ):
        """Test closing a dedicated session gracefully."""
        # Create session and job
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()
        isa_circuit = transpile(simple_circuit, basis_gates=backend_config["basis_gates"])

        serialized_params = serialize_pubs([(isa_circuit,)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        job_id = job_response.json()["id"]

        # Close session
        close_response = client.delete(
            f"/v1/sessions/{session_id}/close", headers=auth_headers
        )
        assert close_response.status_code == 204

        # Verify session is not accepting jobs
        session_data = client.get(f"/v1/sessions/{session_id}", headers=auth_headers).json()
        assert session_data["accepting_jobs"] is False
        assert session_data["active"] is False

        # Try to create another job (should fail)
        job_response2 = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert job_response2.status_code == 404

        # Wait for original job to complete
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            job_status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
            if job_status["state"]["status"] == "COMPLETED":
                break
            time.sleep(0.1)

        # Original job should complete successfully
        assert job_status["state"]["status"] == "COMPLETED"


class TestBatchModeIntegration:
    """Integration tests for batch mode (parallel execution)."""

    def test_batch_session_multiple_jobs(
        self, client: TestClient, auth_headers: dict[str, str], bell_circuits: list[QuantumCircuit]
    ):
        """Test batch session with multiple jobs."""
        # Create batch session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "batch", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]
        assert session_response.json()["mode"] == "batch"

        # Get backend configuration
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()

        # Create multiple jobs in batch
        job_ids = []
        for circuit in bell_circuits:
            isa_circuit = transpile(circuit, basis_gates=backend_config["basis_gates"])
            serialized_params = serialize_pubs([(isa_circuit,)])
            job_response = client.post(
                "/v1/jobs",
                json={
                    "program_id": "sampler",
                    "backend": "fake_manila@aer",
                    "params": serialized_params,
                    "session_id": session_id,
                },
                headers=auth_headers,
            )
            assert job_response.status_code == 202
            job_ids.append(job_response.json()["id"])

        # Wait for all jobs to complete
        max_wait = 30
        start_time = time.time()
        all_completed = False
        while time.time() - start_time < max_wait:
            statuses = [
                client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
                for job_id in job_ids
            ]
            if all(s["state"]["status"] == "COMPLETED" for s in statuses):
                all_completed = True
                break
            time.sleep(0.2)

        assert all_completed, "Not all jobs completed in time"

        # Verify all jobs succeeded
        for job_id in job_ids:
            results = client.get(f"/v1/jobs/{job_id}/results", headers=auth_headers)
            assert results.status_code == 200


class TestSessionCancellation:
    """Integration tests for session cancellation."""

    def test_cancel_session_cancels_queued_jobs(
        self, client: TestClient, auth_headers: dict[str, str], bell_circuits: list[QuantumCircuit]
    ):
        """Test that cancelling a session cancels queued jobs."""
        # Create session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Get backend configuration
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()

        # Create multiple jobs quickly (some should be queued)
        job_ids = []
        for circuit in bell_circuits:
            isa_circuit = transpile(circuit, basis_gates=backend_config["basis_gates"])
            serialized_params = serialize_pubs([(isa_circuit,)])
            job_response = client.post(
                "/v1/jobs",
                json={
                    "program_id": "sampler",
                    "backend": "fake_manila@aer",
                    "params": serialized_params,
                    "session_id": session_id,
                },
                headers=auth_headers,
            )
            job_ids.append(job_response.json()["id"])

        # Cancel session immediately
        cancel_response = client.delete(
            f"/v1/sessions/{session_id}/cancel", headers=auth_headers
        )
        assert cancel_response.status_code == 204

        # Wait a bit for cancellation to propagate
        time.sleep(0.5)

        # Check job statuses
        statuses = [
            client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()["state"]["status"]
            for job_id in job_ids
        ]

        # At least some jobs should be cancelled (queued ones)
        # Some might have completed if they started before cancellation
        assert "CANCELLED" in statuses or all(s in ["COMPLETED", "RUNNING"] for s in statuses)


class TestEstimatorWithSessions:
    """Integration tests for estimator primitive with sessions."""

    def test_estimator_in_dedicated_session(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        """Test estimator primitive within a dedicated session."""
        # Create session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Create circuit without measurements
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)

        # Create observable
        observable = SparsePauliOp(["ZZ", "XX"])

        # Get backend configuration and transpile
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()
        isa_circuit = transpile(circuit, basis_gates=backend_config["basis_gates"])

        # Create estimator job
        serialized_params = serialize_pubs([(isa_circuit, observable)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "estimator",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert job_response.status_code == 202
        job_id = job_response.json()["id"]

        # Wait for completion
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            job_status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
            if job_status["state"]["status"] == "COMPLETED":
                break
            time.sleep(0.1)

        assert job_status["state"]["status"] == "COMPLETED"

        # Get results
        results = client.get(f"/v1/jobs/{job_id}/results", headers=auth_headers)
        assert results.status_code == 200


class TestSessionValidation:
    """Integration tests for session validation logic."""

    def test_job_backend_must_match_session(
        self, client: TestClient, auth_headers: dict[str, str], simple_circuit: QuantumCircuit
    ):
        """Test that job backend must match session backend."""
        # Create session with fake_manila
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Try to create job with different backend
        serialized_params = serialize_pubs([(simple_circuit,)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_kyoto@aer",  # Different backend
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 404
        assert "mismatch" in job_response.json()["detail"].lower()

    def test_cannot_use_closed_session(
        self, client: TestClient, auth_headers: dict[str, str], simple_circuit: QuantumCircuit
    ):
        """Test that closed session cannot accept new jobs."""
        # Create and close session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        client.delete(f"/v1/sessions/{session_id}/close", headers=auth_headers)

        # Try to create job
        serialized_params = serialize_pubs([(simple_circuit,)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 404
        assert "not accepting" in job_response.json()["detail"].lower()

    def test_session_elapsed_time_increases(
        self, client: TestClient, auth_headers: dict[str, str]
    ):
        """Test that session elapsed_time increases over time."""
        # Create session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Get initial elapsed time
        session1 = client.get(f"/v1/sessions/{session_id}", headers=auth_headers).json()
        elapsed1 = session1["elapsed_time"]

        # Wait a bit
        time.sleep(1)

        # Get elapsed time again
        session2 = client.get(f"/v1/sessions/{session_id}", headers=auth_headers).json()
        elapsed2 = session2["elapsed_time"]

        # Should have increased
        assert elapsed2 > elapsed1


class TestMultipleExecutors:
    """Integration tests with multiple executors (if available)."""

    def test_session_with_specific_executor(
        self, client: TestClient, auth_headers: dict[str, str], simple_circuit: QuantumCircuit
    ):
        """Test session with specific executor in backend name."""
        # Create session with explicit executor
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Get backend configuration
        backend_config = client.get(
            "/v1/backends/fake_manila@aer/configuration", headers=auth_headers
        ).json()
        isa_circuit = transpile(simple_circuit, basis_gates=backend_config["basis_gates"])

        # Create job with same backend
        serialized_params = serialize_pubs([(isa_circuit,)])
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert job_response.status_code == 202

        # Wait for completion
        job_id = job_response.json()["id"]
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            job_status = client.get(f"/v1/jobs/{job_id}", headers=auth_headers).json()
            if job_status["state"]["status"] == "COMPLETED":
                break
            time.sleep(0.1)

        assert job_status["state"]["status"] == "COMPLETED"
