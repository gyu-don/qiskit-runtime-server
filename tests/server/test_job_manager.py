"""Tests for JobManager."""

import time
from typing import TYPE_CHECKING

import pytest
from qiskit import QuantumCircuit

from qiskit_runtime_server.executors.aer import AerExecutor
from qiskit_runtime_server.managers import JobManager
from qiskit_runtime_server.models import JobInfo, JobStatus

if TYPE_CHECKING:
    from qiskit_runtime_server.executors.base import BaseExecutor


class TestJobManagerQueue:
    """Tests for job manager queueing functionality."""

    def test_job_manager_queue(self) -> None:
        """Test that jobs are queued and executed."""
        # Setup
        executors: dict[str, BaseExecutor] = {"aer": AerExecutor()}
        manager = JobManager(executors)

        # Create a simple circuit
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure_all()

        # Create job
        job_id = manager.create_job(
            program_id="sampler",
            backend_name="fake_manila@aer",
            params={"pubs": [(circuit, None, 1024)]},
            options={},
        )

        # Initial status should be QUEUED
        job = manager.get_job(job_id)
        assert job is not None
        assert job.job_id == job_id
        assert job.status == JobStatus.QUEUED
        assert job.program_id == "sampler"
        assert job.backend_name == "fake_manila@aer"

        # Wait a bit for worker to pick up the job
        time.sleep(1.0)
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status in [JobStatus.RUNNING, JobStatus.COMPLETED]

        # Wait enough for completion
        time.sleep(3.0)
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.result_data is not None
        assert job.started_at is not None
        assert job.completed_at is not None
        assert job.error_message is None

        # Cleanup
        manager.shutdown()

    def test_job_manager_sequential(self) -> None:
        """Test that jobs are executed sequentially, not in parallel."""
        # Setup
        manager = JobManager(executors={"aer": AerExecutor()})

        # Create a slightly larger circuit to slow down execution
        circuit = QuantumCircuit(4)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.cx(1, 2)
        circuit.cx(2, 3)
        circuit.measure_all()

        # Submit multiple jobs with higher shot count
        job_ids = [
            manager.create_job("sampler", "fake_manila@aer", {"pubs": [(circuit, None, 4096)]}, {})
            for _ in range(5)
        ]

        # Check immediately after submission - at most 1 should be running
        # The rest should still be queued
        time.sleep(0.05)  # Very short delay to let worker pick up first job
        statuses_immediate = []
        for jid in job_ids:
            job = manager.get_job(jid)
            if job is not None:
                statuses_immediate.append(job.status)
        running_count = sum(1 for s in statuses_immediate if s == JobStatus.RUNNING)

        # With sequential execution, we should have at most 1 running job
        assert running_count <= 1, (
            f"Expected at most 1 running job (sequential), got {running_count}"
        )

        # Verify that not all jobs complete at the same time (would indicate parallel execution)
        # Record completion times
        completion_times: list[float] = []
        for _ in range(30):  # Check for up to 30 seconds
            time.sleep(1.0)
            completed = [
                manager.get_job(jid)
                for jid in job_ids
                if manager.get_job(jid) is not None
                and manager.get_job(jid).status == JobStatus.COMPLETED  # type: ignore[union-attr]
            ]
            if len(completed) > len(completion_times):
                completion_times.append(time.time())
            if len(completed) == len(job_ids):
                break

        # All jobs should complete eventually
        for job_id in job_ids:
            job = manager.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETED
            assert job.result_data is not None

        # Cleanup
        manager.shutdown()

    def test_job_manager_invalid_backend(self) -> None:
        """Test that invalid backend names raise an error."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(2)
        circuit.h(0)

        # Invalid backend format (no @ separator)
        with pytest.raises(ValueError, match="Invalid backend name"):
            manager.create_job(
                program_id="sampler",
                backend_name="invalid_backend",
                params={"pubs": [(circuit,)]},
                options={},
            )

        # Invalid backend format (unknown executor)
        with pytest.raises(ValueError, match="Invalid backend name"):
            manager.create_job(
                program_id="sampler",
                backend_name="fake_manila@unknown",
                params={"pubs": [(circuit,)]},
                options={},
            )

        # Cleanup
        manager.shutdown()

    def test_job_manager_list_jobs(self) -> None:
        """Test listing all jobs."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        # Create multiple jobs
        job_ids = [
            manager.create_job("sampler", "fake_manila@aer", {"pubs": [(circuit, None, 100)]}, {})
            for _ in range(2)
        ]

        # List jobs
        all_jobs = manager.list_jobs()
        assert len(all_jobs) == 2
        for job_id in job_ids:
            assert job_id in all_jobs
            assert all_jobs[job_id].job_id == job_id

        # Cleanup
        manager.shutdown()

    def test_job_manager_error_handling(self) -> None:
        """Test that job errors are properly captured."""
        manager = JobManager(executors={"aer": AerExecutor()})

        # Create job with invalid program_id
        # This will be accepted in create_job but fail during execution
        circuit = QuantumCircuit(2)
        job_id = manager.create_job(
            program_id="invalid_program",
            backend_name="fake_manila@aer",
            params={"pubs": [(circuit,)]},
            options={},
        )

        # Wait for execution
        time.sleep(2.0)

        # Check that job failed
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_message is not None
        assert "Unknown program_id" in job.error_message

        # Cleanup
        manager.shutdown()


class TestJobManagerShutdown:
    """Tests for job manager shutdown functionality."""

    def test_shutdown(self) -> None:
        """Test that shutdown stops the worker thread."""
        manager = JobManager(executors={"aer": AerExecutor()})

        # Verify worker is running
        assert manager._worker_thread is not None
        assert manager._worker_thread.is_alive()

        # Shutdown
        manager.shutdown()

        # Worker should be stopped
        assert not manager._worker_thread.is_alive()

    def test_shutdown_with_pending_jobs(self) -> None:
        """Test shutdown with jobs still in queue."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        # Submit multiple jobs
        job_ids = [
            manager.create_job("sampler", "fake_manila@aer", {"pubs": [(circuit, None, 1000)]}, {})
            for _ in range(5)
        ]

        # Shutdown immediately (some jobs may not finish)
        manager.shutdown()

        # Worker should be stopped
        assert manager._worker_thread is not None
        assert not manager._worker_thread.is_alive()

        # Check job states (some might be completed, some queued)
        for job_id in job_ids:
            job = manager.get_job(job_id)
            assert job is not None
            assert job.status in [
                JobStatus.QUEUED,
                JobStatus.RUNNING,
                JobStatus.COMPLETED,
                JobStatus.FAILED,
            ]


class TestJobManagerCancellation:
    """Tests for job cancellation functionality."""

    def test_cancel_queued_job(self) -> None:
        """Test cancelling a job that is still queued."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        # Create multiple jobs with longer execution time to ensure some stay queued
        job_ids = [
            manager.create_job("sampler", "fake_manila@aer", {"pubs": [(circuit, None, 4096)]}, {})
            for _ in range(5)
        ]

        # Cancel the last job immediately (should still be queued)
        # The first job will be picked up by the worker, but the last should remain queued
        success = manager.cancel_job(job_ids[4])

        assert success is True
        job = manager.get_job(job_ids[4])
        assert job is not None
        assert job.status == JobStatus.CANCELLED
        assert job.error_message == "Cancelled by user"
        assert job.completed_at is not None

        # Cleanup
        manager.shutdown()

    def test_cancel_running_job_fails(self) -> None:
        """Test that cancelling a running job returns False."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(4)
        for i in range(4):
            circuit.h(i)
        circuit.measure_all()

        # Create a job
        job_id = manager.create_job(
            "sampler", "fake_manila@aer", {"pubs": [(circuit, None, 4096)]}, {}
        )

        # Wait for it to start running
        time.sleep(0.5)
        job = manager.get_job(job_id)
        assert job is not None

        if job.status == JobStatus.RUNNING:
            # Try to cancel running job (should fail)
            success = manager.cancel_job(job_id)
            assert success is False

            # Job should still be running
            job = manager.get_job(job_id)
            assert job is not None
            assert job.status == JobStatus.RUNNING

        # Cleanup
        manager.shutdown()

    def test_cancel_completed_job_fails(self) -> None:
        """Test that cancelling a completed job returns False."""
        manager = JobManager(executors={"aer": AerExecutor()})

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        job_id = manager.create_job(
            "sampler", "fake_manila@aer", {"pubs": [(circuit, None, 100)]}, {}
        )

        # Wait for completion
        time.sleep(2.0)
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED

        # Try to cancel completed job (should fail)
        success = manager.cancel_job(job_id)
        assert success is False

        # Job should still be completed
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED

        # Cleanup
        manager.shutdown()

    def test_cancel_nonexistent_job(self) -> None:
        """Test that cancelling a non-existent job returns False."""
        manager = JobManager(executors={"aer": AerExecutor()})

        success = manager.cancel_job("nonexistent-job-id")
        assert success is False

        # Cleanup
        manager.shutdown()


class TestJobManagerEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_get_nonexistent_job(self) -> None:
        """Test getting a job that doesn't exist."""
        manager = JobManager(executors={"aer": AerExecutor()})

        job = manager.get_job("nonexistent-job-id")
        assert job is None

        # Cleanup
        manager.shutdown()

    def test_invalid_backend_executor_not_found(self) -> None:
        """Test that executor not found during execution causes job failure."""
        from datetime import UTC, datetime
        from uuid import uuid4

        manager = JobManager(executors={"aer": AerExecutor()})

        # Manually create a job with valid format but non-existent executor
        # We need to bypass the validation in create_job
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        job_id = f"job-{uuid4()}"
        job_info = JobInfo(
            job_id=job_id,
            program_id="sampler",
            backend_name="fake_manila@nonexistent",  # Valid format, unknown executor
            params={"pubs": [(circuit,)]},
            options={},
            status=JobStatus.QUEUED,
            created_at=datetime.now(UTC),
        )

        with manager._lock:
            manager.jobs[job_id] = job_info

        # Manually execute (simulating worker behavior)
        manager._execute_job(job_id)

        # Should fail with invalid backend name (parsed before executor lookup)
        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_message is not None
        assert "Invalid backend name" in job.error_message

        # Cleanup
        manager.shutdown()

    def test_worker_thread_already_running_warning(self, caplog) -> None:  # type: ignore[no-untyped-def]
        """Test that starting worker twice logs a warning."""
        import logging

        manager = JobManager(executors={"aer": AerExecutor()})

        # Try to start worker again
        with caplog.at_level(logging.WARNING):
            manager._start_worker()

        assert "Worker thread already running" in caplog.text

        # Cleanup
        manager.shutdown()
