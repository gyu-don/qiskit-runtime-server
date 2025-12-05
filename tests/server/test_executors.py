"""Tests for executor implementations."""

from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp

from qiskit_runtime_server.executors import AerExecutor, BaseExecutor


class TestAerExecutor:
    """Tests for AerExecutor implementation."""

    def test_executor_name(self) -> None:
        """Test that executor returns correct name."""
        executor = AerExecutor()
        assert executor.name == "aer"

    def test_executor_is_base_executor(self) -> None:
        """Test that AerExecutor inherits from BaseExecutor."""
        executor = AerExecutor()
        assert isinstance(executor, BaseExecutor)

    def test_execute_sampler_basic(self) -> None:
        """Test sampler execution with a simple circuit."""
        executor = AerExecutor()

        # Create a simple Bell state circuit
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)
        circuit.measure_all()

        # Execute sampler
        pubs = [(circuit,)]
        result = executor.execute_sampler(
            pubs=pubs, options={"default_shots": 1024}, backend_name="fake_manila"
        )

        # Verify result structure
        assert result is not None
        assert len(result) == 1
        pub_result = result[0]

        # Check that we got measurement data
        assert hasattr(pub_result, "data")
        assert hasattr(pub_result.data, "meas")

    def test_execute_sampler_custom_shots(self) -> None:
        """Test sampler with custom shots setting."""
        executor = AerExecutor(shots=2048)

        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        pubs = [(circuit,)]
        result = executor.execute_sampler(
            pubs=pubs, options={"default_shots": 512}, backend_name="fake_manila"
        )

        assert result is not None
        assert len(result) == 1

    def test_execute_estimator_basic(self) -> None:
        """Test estimator execution with a simple circuit and observable."""
        executor = AerExecutor()

        # Create a simple circuit
        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)

        # Create observable (Z0)
        observable = SparsePauliOp(["ZI"])

        # Execute estimator
        pubs = [(circuit, observable)]
        result = executor.execute_estimator(pubs=pubs, options={}, backend_name="fake_manila")

        # Verify result structure
        assert result is not None
        assert len(result) == 1
        pub_result = result[0]

        # Check that we got expectation value data
        assert hasattr(pub_result, "data")
        assert hasattr(pub_result.data, "evs")

    def test_backend_name_parameter_accepted(self) -> None:
        """Test that backend_name parameter is accepted (even if unused)."""
        executor = AerExecutor()

        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        # Should work with any backend name (not validated currently)
        pubs = [(circuit,)]
        result = executor.execute_sampler(
            pubs=pubs, options={"default_shots": 100}, backend_name="any_backend"
        )

        assert result is not None

    def test_seed_simulator_reproducibility(self) -> None:
        """Test that seed produces reproducible results."""
        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        pubs = [(circuit,)]
        options = {"default_shots": 1024}

        # Run twice with same seed
        executor1 = AerExecutor(seed_simulator=42)
        result1 = executor1.execute_sampler(pubs=pubs, options=options, backend_name="fake_manila")

        executor2 = AerExecutor(seed_simulator=42)
        result2 = executor2.execute_sampler(pubs=pubs, options=options, backend_name="fake_manila")

        # Results should be identical
        assert result1[0].data.meas.get_counts() == result2[0].data.meas.get_counts()

    def test_options_shots_override(self) -> None:
        """Test that options default_shots overrides executor default."""
        executor = AerExecutor(shots=1024)

        circuit = QuantumCircuit(1)
        circuit.h(0)
        circuit.measure_all()

        # options["default_shots"] should override executor default
        result = executor.execute_sampler(
            pubs=[(circuit,)],
            options={"default_shots": 2048},
            backend_name="fake_manila",
        )

        # Should use options default_shots (2048), not executor default (1024)
        assert result[0].data.meas.num_shots == 2048


class TestAerExecutorOptions:
    """Tests for AerExecutor option handling."""

    def test_max_parallel_threads_option(self):
        """Test that max_parallel_threads is applied."""
        executor = AerExecutor(max_parallel_threads=4)

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.measure_all()

        # Execute and verify it doesn't crash
        result = executor.execute_sampler(
            pubs=[(circuit, None, 100)], options={}, backend_name="fake_manila"
        )

        assert result is not None
        assert len(result) == 1

    def test_estimator_with_precision(self):
        """Test estimator with explicit precision option."""
        executor = AerExecutor()

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)

        observable = SparsePauliOp(["ZZ", "ZI"])

        # Execute with precision
        result = executor.execute_estimator(
            pubs=[(circuit, observable)],
            options={"default_precision": 0.01},
            backend_name="fake_manila",
        )

        assert result is not None
        assert len(result) == 1

    def test_estimator_without_precision(self):
        """Test estimator without precision option (default behavior)."""
        executor = AerExecutor()

        circuit = QuantumCircuit(2)
        circuit.h(0)
        circuit.cx(0, 1)

        observable = SparsePauliOp(["II"])

        # Execute without precision (should use default)
        result = executor.execute_estimator(
            pubs=[(circuit, observable)], options={}, backend_name="fake_manila"
        )

        assert result is not None
        assert len(result) == 1
