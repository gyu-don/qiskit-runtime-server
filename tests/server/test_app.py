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
        assert data["status"] in [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.COMPLETED]

    def test_get_job_status_not_found(self, client):
        """Test getting status of non-existent job."""
        response = client.get("/v1/jobs/non-existent-job")
        assert response.status_code == 404

    def test_get_job_results(self, client, simple_circuit):
        """Test GET /v1/jobs/{job_id}/results."""
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

        # Wait for completion/failure
        max_wait = 10
        for _ in range(max_wait):
            response = client.get(f"/v1/jobs/{job_id}")
            status = response.json()["status"]
            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            time.sleep(1)

        # Get results
        response = client.get(f"/v1/jobs/{job_id}/results")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == job_id
        assert data["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]
        assert "results" in data

        # If completed, verify results are properly serialized
        if data["status"] == JobStatus.COMPLETED:
            assert data["results"] is not None
            # Results should be dict (serialized PrimitiveResult)
            assert isinstance(data["results"], dict)

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

            status = response.json()["status"]
            statuses_seen.add(status)

            if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            time.sleep(1)

        # Should have completed or failed
        assert (JobStatus.COMPLETED in statuses_seen) or (JobStatus.FAILED in statuses_seen)

        # 3. Get results
        response = client.get(f"/v1/jobs/{job_id}/results")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]
        assert "results" in data

        # If completed, verify results are properly serialized
        if data["status"] == JobStatus.COMPLETED:
            assert data["results"] is not None
            assert isinstance(data["results"], dict)
