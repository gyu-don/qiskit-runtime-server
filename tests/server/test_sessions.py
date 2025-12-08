"""Tests for session management endpoints."""

import pytest
from fastapi.testclient import TestClient

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


class TestCreateSession:
    """Tests for session creation."""

    def test_create_dedicated_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a dedicated mode session."""
        response = client.post(
            "/v1/sessions",
            json={
                "mode": "dedicated",
                "backend": "fake_manila@aer",
                "max_ttl": 3600,
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "dedicated"
        assert data["backend"] == "fake_manila@aer"
        assert data["max_ttl"] == 3600
        assert data["accepting_jobs"] is True
        assert data["active"] is True
        assert data["jobs"] == []
        assert "id" in data
        assert data["id"].startswith("session-")

    def test_create_batch_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a batch mode session."""
        response = client.post(
            "/v1/sessions",
            json={
                "mode": "batch",
                "backend": "fake_manila@aer",
                "max_ttl": 7200,
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["mode"] == "batch"
        assert data["backend"] == "fake_manila@aer"
        assert data["max_ttl"] == 7200

    def test_create_session_with_instance(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a session with instance CRN."""
        response = client.post(
            "/v1/sessions",
            json={
                "mode": "dedicated",
                "backend": "fake_manila@aer",
                "instance": "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test",
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["instance"] == "crn:v1:bluemix:public:quantum-computing:us-east:a/test::test"

    def test_create_session_invalid_backend(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a session with invalid backend."""
        response = client.post(
            "/v1/sessions",
            json={
                "mode": "dedicated",
                "backend": "invalid_backend",
            },
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestGetSession:
    """Tests for retrieving session information."""

    def test_get_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test getting session details."""
        # Create session
        create_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = create_response.json()["id"]

        # Get session
        response = client.get(f"/v1/sessions/{session_id}", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == session_id
        assert data["mode"] == "dedicated"
        assert "elapsed_time" in data

    def test_get_nonexistent_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test getting a nonexistent session."""
        response = client.get("/v1/sessions/session-nonexistent", headers=auth_headers)

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestUpdateSession:
    """Tests for updating session settings."""

    def test_update_accepting_jobs(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test updating accepting_jobs flag."""
        # Create session
        create_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = create_response.json()["id"]

        # Update session
        response = client.patch(
            f"/v1/sessions/{session_id}",
            json={"accepting_jobs": False},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accepting_jobs"] is False

    def test_update_nonexistent_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test updating a nonexistent session."""
        response = client.patch(
            "/v1/sessions/session-nonexistent",
            json={"accepting_jobs": False},
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCloseSession:
    """Tests for closing sessions."""

    def test_close_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test closing a session gracefully."""
        # Create session
        create_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = create_response.json()["id"]

        # Close session
        response = client.delete(f"/v1/sessions/{session_id}/close", headers=auth_headers)

        assert response.status_code == 204

        # Verify session is closed
        get_response = client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["accepting_jobs"] is False
        assert data["active"] is False

    def test_close_nonexistent_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test closing a nonexistent session."""
        response = client.delete("/v1/sessions/session-nonexistent/close", headers=auth_headers)

        assert response.status_code == 404


class TestCancelSession:
    """Tests for cancelling sessions."""

    def test_cancel_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test cancelling a session."""
        # Create session
        create_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = create_response.json()["id"]

        # Cancel session
        response = client.delete(f"/v1/sessions/{session_id}/cancel", headers=auth_headers)

        assert response.status_code == 204

        # Verify session is cancelled
        get_response = client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["accepting_jobs"] is False
        assert data["active"] is False

    def test_cancel_nonexistent_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test cancelling a nonexistent session."""
        response = client.delete("/v1/sessions/session-nonexistent/cancel", headers=auth_headers)

        assert response.status_code == 404


class TestSessionJobIntegration:
    """Tests for session-job integration."""

    def test_create_job_with_session(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a job associated with a session."""
        # Create session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Create job with session
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": {"pubs": []},
                "session_id": session_id,
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 202
        job_id = job_response.json()["id"]

        # Verify job is in session
        session_get_response = client.get(f"/v1/sessions/{session_id}", headers=auth_headers)
        assert session_get_response.status_code == 200
        session_data = session_get_response.json()
        assert job_id in session_data["jobs"]

    def test_create_job_with_nonexistent_session(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a job with nonexistent session."""
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": {"pubs": []},
                "session_id": "session-nonexistent",
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 404
        assert "not found" in job_response.json()["detail"].lower()

    def test_create_job_backend_mismatch(self, client: TestClient, auth_headers: dict[str, str]) -> None:
        """Test creating a job with backend that doesn't match session backend."""
        # Create session with fake_manila
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Try to create job with different backend
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_kyoto@aer",  # Different backend
                "params": {"pubs": []},
                "session_id": session_id,
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 404
        assert "mismatch" in job_response.json()["detail"].lower()

    def test_create_job_session_not_accepting(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """Test creating a job when session is not accepting jobs."""
        # Create session
        session_response = client.post(
            "/v1/sessions",
            json={"mode": "dedicated", "backend": "fake_manila@aer"},
            headers=auth_headers,
        )
        session_id = session_response.json()["id"]

        # Close session
        client.delete(f"/v1/sessions/{session_id}/close", headers=auth_headers)

        # Try to create job
        job_response = client.post(
            "/v1/jobs",
            json={
                "program_id": "sampler",
                "backend": "fake_manila@aer",
                "params": {"pubs": []},
                "session_id": session_id,
            },
            headers=auth_headers,
        )

        assert job_response.status_code == 404
        assert "not accepting" in job_response.json()["detail"].lower()
