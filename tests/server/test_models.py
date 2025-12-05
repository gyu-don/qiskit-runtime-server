"""Tests for data models."""

from datetime import UTC, datetime

from qiskit_runtime_server.models import JobInfo, JobStatus


class TestJobStatus:
    """Tests for JobStatus enum."""

    def test_job_status_values(self):
        """Test that JobStatus enum has all expected values."""
        assert JobStatus.QUEUED == "QUEUED"
        assert JobStatus.RUNNING == "RUNNING"
        assert JobStatus.COMPLETED == "COMPLETED"
        assert JobStatus.FAILED == "FAILED"
        assert JobStatus.CANCELLED == "CANCELLED"

    def test_job_status_enum(self):
        """Test that JobStatus is a proper enum."""
        # All status values should be instances of JobStatus
        assert isinstance(JobStatus.QUEUED, JobStatus)
        assert isinstance(JobStatus.RUNNING, JobStatus)
        assert isinstance(JobStatus.COMPLETED, JobStatus)
        assert isinstance(JobStatus.FAILED, JobStatus)
        assert isinstance(JobStatus.CANCELLED, JobStatus)


class TestJobInfo:
    """Tests for JobInfo model."""

    def test_job_info_creation(self):
        """Test creating a JobInfo instance with required fields."""
        info = JobInfo(
            job_id="test-job",
            program_id="sampler",
            backend_name="fake_manila@aer",
            params={"pubs": []},
            options={},
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        assert info.job_id == "test-job"
        assert info.program_id == "sampler"
        assert info.backend_name == "fake_manila@aer"
        assert info.params == {"pubs": []}
        assert info.options == {}
        assert info.status == JobStatus.QUEUED
        assert isinstance(info.created_at, datetime)

    def test_job_info_optional_fields(self):
        """Test that optional fields default to None."""
        info = JobInfo(
            job_id="test-job",
            program_id="sampler",
            backend_name="fake_manila@aer",
            params={},
            options={},
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        assert info.started_at is None
        assert info.completed_at is None
        assert info.result_data is None
        assert info.error_message is None

    def test_job_info_with_all_fields(self):
        """Test creating a JobInfo with all fields populated."""
        now = datetime.now(UTC)
        started = datetime.now(UTC)
        completed = datetime.now(UTC)

        info = JobInfo(
            job_id="test-job-complete",
            program_id="estimator",
            backend_name="fake_kyoto@aer",
            params={"pubs": [{"circuit": "qc", "observables": "obs"}]},
            options={"shots": 1024},
            status=JobStatus.COMPLETED,
            created_at=now,
            started_at=started,
            completed_at=completed,
            result_data={"result": "data"},
            error_message=None,
        )

        assert info.job_id == "test-job-complete"
        assert info.status == JobStatus.COMPLETED
        assert info.started_at == started
        assert info.completed_at == completed
        assert info.result_data == {"result": "data"}
        assert info.error_message is None

    def test_job_info_status_transitions(self):
        """Test that status can be updated."""
        info = JobInfo(
            job_id="test-job",
            program_id="sampler",
            backend_name="fake_manila@aer",
            params={},
            options={},
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        # Status should start as QUEUED
        assert info.status == JobStatus.QUEUED

        # Status can be changed to RUNNING
        info.status = JobStatus.RUNNING
        assert info.status == JobStatus.RUNNING

        # Status can be changed to COMPLETED
        info.status = JobStatus.COMPLETED
        assert info.status == JobStatus.COMPLETED

    def test_job_info_with_error(self):
        """Test JobInfo with error information."""
        info = JobInfo(
            job_id="test-job-failed",
            program_id="sampler",
            backend_name="fake_manila@aer",
            params={},
            options={},
            status=JobStatus.FAILED,
            created_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            error_message="Execution failed: Invalid circuit",
        )

        assert info.status == JobStatus.FAILED
        assert info.error_message == "Execution failed: Invalid circuit"
        assert info.result_data is None
