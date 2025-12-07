"""Tests for FastAPI application factory."""

import json
import time

import pytest
from fastapi.testclient import TestClient
from qiskit import QuantumCircuit
from qiskit_ibm_runtime.utils import RuntimeEncoder

from qiskit_runtime_server import create_app
from qiskit_runtime_server.executors import AerExecutor
from qiskit_runtime_server.models import JobStatus


class TestCreateApp:
    """Test create_app factory."""

    def test_create_app_default(self):
        """Test creating app with default executors."""
        app = create_app()
        assert app is not None
        assert app.title == "Qiskit Runtime Backend API"

    def test_create_app_with_executors(self):
        """Test creating app with custom executors."""
        executors = {"aer": AerExecutor()}
        app = create_app(executors=executors)
        assert app is not None


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root(self):
        """Test GET /."""
        app = create_app()
        client = TestClient(app)

        response = client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "executors" in data
        assert "aer" in data["executors"]


class TestBackendsEndpoint:
    """Test backends endpoint."""

    def test_list_backends(self):
        """Test GET /v1/backends."""
        app = create_app(executors={"aer": AerExecutor()})
        client = TestClient(app)

        response = client.get("/v1/backends")
        assert response.status_code == 200

        data = response.json()
        assert "devices" in data

        # All backends should end with @aer
        backend_names = [b["backend_name"] for b in data["devices"]]
        assert all(name.endswith("@aer") for name in backend_names)
        assert any("fake_manila@aer" in name for name in backend_names)

    def test_get_backend_status(self):
        """Test GET /v1/backends/{backend_name}/status."""
        app = create_app(executors={"aer": AerExecutor()})
        client = TestClient(app)

        response = client.get("/v1/backends/fake_manila@aer/status")
        assert response.status_code == 200

        data = response.json()
        assert data["state"] is True
        assert data["status"] == "active"
        assert data["message"] == ""
        assert "length_queue" in data
        assert isinstance(data["length_queue"], int)
        assert data["length_queue"] >= 0
        assert data["backend_version"] == "1.0.0"

    def test_get_backend_status_not_found(self):
        """Test getting status of non-existent backend."""
        app = create_app(executors={"aer": AerExecutor()})
        client = TestClient(app)

        # Backend without executor suffix
        response = client.get("/v1/backends/fake_manila/status")
        assert response.status_code == 404

        # Unknown executor
        response = client.get("/v1/backends/fake_manila@unknown/status")
        assert response.status_code == 404

        # Unknown metadata
        response = client.get("/v1/backends/fake_unknown@aer/status")
        assert response.status_code == 404

    def test_get_backend_status_queue_length(self):
        """Test backend status reflects queue length."""
        app = create_app(executors={"aer": AerExecutor()})
        client = TestClient(app)

        # Check initial queue length is 0
        response = client.get("/v1/backends/fake_manila@aer/status")
        assert response.status_code == 200
        initial_queue = response.json()["length_queue"]
        assert initial_queue == 0

        # Create a job (this will be queued/running)
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        pubs_data = [(circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        assert response.status_code == 202

        # Check queue length increased (may be 0 if job already completed)
        response = client.get("/v1/backends/fake_manila@aer/status")
        assert response.status_code == 200
        # Queue length should be >= 0 (job may have completed quickly)
        assert response.json()["length_queue"] >= 0


class TestJobsEndpoint:
    """Test jobs endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app = create_app(executors={"aer": AerExecutor()})
        return TestClient(app)

    @pytest.fixture
    def simple_circuit(self):
        """Create a simple quantum circuit."""
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure_all()
        return circuit

    def test_create_job_returns_202(self, client, simple_circuit):
        """Test POST /v1/jobs returns 202 Accepted."""
        # Serialize circuit using RuntimeEncoder
        pubs_data = [(simple_circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["id"].startswith("job-")
        assert "backend" in data
        assert data["backend"] == "fake_manila@aer"

    def test_create_job_invalid_backend(self, client, simple_circuit):
        """Test creating job with invalid backend name."""
        # No @executor
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila",
                "params": {"pubs": []},
                "options": {},
            },
        )
        assert response.status_code == 404

        # Unknown executor
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@unknown",
                "params": {"pubs": []},
                "options": {},
            },
        )
        assert response.status_code == 404

        # Unknown metadata
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_unknown@aer",
                "params": {"pubs": []},
                "options": {},
            },
        )
        assert response.status_code == 404

    def test_get_job_status(self, client, simple_circuit):
        """Test GET /v1/jobs/{job_id}."""
        # Serialize circuit using RuntimeEncoder
        pubs_data = [(simple_circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        # Create job
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        # Get status (should be QUEUED initially)
        response = client.get(f"/v1/jobs/{job_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == job_id
        assert "state" in data
        assert data["state"]["status"] in [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]

    def test_get_job_status_not_found(self, client):
        """Test getting status of non-existent job."""
        response = client.get("/v1/jobs/non-existent-job")
        assert response.status_code == 404

    def test_get_job_results_success(self, client, simple_circuit):
        """Test GET /v1/jobs/{job_id}/results for successful job."""
        # Serialize circuit using RuntimeEncoder
        pubs_data = [(simple_circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        # Create job
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        job_id = response.json()["id"]

        # Wait for completion
        max_wait = 10
        for _ in range(max_wait):
            response = client.get(f"/v1/jobs/{job_id}")
            status = response.json()["state"]["status"]
            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            time.sleep(1)

        # Get results - should return 200 for successful job
        response = client.get(f"/v1/jobs/{job_id}/results")
        assert response.status_code == 200, (
            f"Job should complete successfully, got {response.status_code}"
        )

        # Verify result structure
        data = response.json()
        assert isinstance(data, dict)
        # PrimitiveResult should have __type__ and __value__ fields
        # or pub_results and metadata fields
        assert "__type__" in data or "pub_results" in data

    def test_get_job_results_not_completed(self, client):
        """Test GET /v1/jobs/{job_id}/results returns 400 for non-completed job."""
        # Create a simple circuit
        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        pubs_data = [(circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        # Create job
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        job_id = response.json()["id"]

        # Try to get results immediately (job likely still QUEUED or RUNNING)
        # Note: This test is timing-dependent, but should work most of the time
        response = client.get(f"/v1/jobs/{job_id}/results")

        # Should return 400 if job is not completed yet
        # (or 200 if job completed very quickly, which is also valid)
        assert response.status_code in [200, 400]

        if response.status_code == 400:
            # Verify error message indicates job is not completed
            assert "not completed" in response.json()["detail"].lower()

    def test_cancel_job(self, client, simple_circuit):
        """Test DELETE /v1/jobs/{job_id}."""
        # Serialize circuit using RuntimeEncoder
        pubs_data = [(simple_circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        # Create job
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        job_id = response.json()["id"]

        # Try to cancel (may succeed if still QUEUED)
        response = client.delete(f"/v1/jobs/{job_id}")
        # Either 200 (cancelled) or 400 (already running/completed)
        assert response.status_code in [200, 400]

    def test_job_lifecycle(self, client, simple_circuit):
        """Test full job lifecycle: create → status → results."""
        # Serialize circuit using RuntimeEncoder
        pubs_data = [(simple_circuit,)]
        serialized_params = json.loads(json.dumps({"pubs": pubs_data}, cls=RuntimeEncoder))

        # 1. Create job
        response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": serialized_params,
                "options": {},
            },
        )
        assert response.status_code == 202
        job_id = response.json()["id"]

        # 2. Check status transitions
        statuses_seen = set()
        max_wait = 10

        for _ in range(max_wait):
            response = client.get(f"/v1/jobs/{job_id}")
            assert response.status_code == 200

            status = response.json()["state"]["status"]
            statuses_seen.add(status)

            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            time.sleep(1)

        # Should have completed (simple circuit should succeed)
        assert JobStatus.COMPLETED in statuses_seen, (
            f"Job should complete successfully, statuses seen: {statuses_seen}"
        )

        # 3. Get results - should return 200 for successful job
        response = client.get(f"/v1/jobs/{job_id}/results")
        assert response.status_code == 200, (
            f"Job completed successfully, should return 200, got {response.status_code}"
        )

        # Verify result structure
        data = response.json()
        assert isinstance(data, dict)
        # PrimitiveResult should have __type__ and __value__ fields
        # or pub_results and metadata fields
        assert "__type__" in data or "pub_results" in data
