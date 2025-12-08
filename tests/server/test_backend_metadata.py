"""Tests for BackendMetadataProvider."""

from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

from qiskit_runtime_server.providers.backend_metadata import (
    BackendMetadataProvider,
    get_backend_metadata_provider,
    reset_backend_metadata_provider,
)


class TestParseBackendName:
    """Tests for parse_backend_name() method."""

    def test_parse_valid_backend_name(self) -> None:
        """Test parsing valid 'metadata@executor' format."""
        provider = BackendMetadataProvider(available_executors=["aer", "custatevec"])

        result = provider.parse_backend_name("fake_manila@aer")
        assert result == ("fake_manila", "aer")

        result = provider.parse_backend_name("fake_manila@custatevec")
        assert result == ("fake_manila", "custatevec")

    def test_parse_backend_name_without_executor(self) -> None:
        """Test parsing backend name without '@executor' suffix."""
        provider = BackendMetadataProvider(available_executors=["aer"])

        result = provider.parse_backend_name("fake_manila")
        assert result is None

    def test_parse_backend_name_unknown_executor(self) -> None:
        """Test parsing backend name with unknown executor."""
        provider = BackendMetadataProvider(available_executors=["aer"])

        result = provider.parse_backend_name("fake_manila@unknown")
        assert result is None

    def test_parse_backend_name_unknown_metadata(self) -> None:
        """Test parsing backend name with unknown metadata."""
        provider = BackendMetadataProvider(available_executors=["aer"])

        result = provider.parse_backend_name("fake_unknown@aer")
        assert result is None


class TestListBackends:
    """Tests for list_backends() method."""

    def test_list_backends_single_executor(self) -> None:
        """Test listing backends with single executor."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        response = provider.list_backends()

        backend_names = [b["backend_name"] for b in response.devices]

        # All backends should end with @aer
        assert all(name.endswith("@aer") for name in backend_names)
        assert "fake_manila@aer" in backend_names

        # Should have base_count × 1 backends
        base_count = len(FakeProviderForBackendV2().backends())
        assert len(backend_names) == base_count

    def test_list_backends_multiple_executors(self) -> None:
        """Test listing backends with multiple executors."""
        provider = BackendMetadataProvider(available_executors=["aer", "custatevec"])
        response = provider.list_backends()

        backend_names = [b["backend_name"] for b in response.devices]

        # Should have both aer and custatevec variants
        assert "fake_manila@aer" in backend_names
        assert "fake_manila@custatevec" in backend_names

        # Should have base_count × 2 backends
        base_count = len(FakeProviderForBackendV2().backends())
        assert len(backend_names) == base_count * 2

    def test_list_backends_contains_metadata(self) -> None:
        """Test that listed backends contain proper metadata."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        response = provider.list_backends()

        # Check first backend has required fields
        first_backend = response.devices[0]
        assert "backend_name" in first_backend
        assert "n_qubits" in first_backend  # FakeProvider uses n_qubits, not num_qubits
        assert "backend_version" in first_backend
        assert first_backend["backend_name"].endswith("@aer")


class TestSingleton:
    """Tests for singleton pattern."""

    def test_provider_singleton(self) -> None:
        """Test that provider is a singleton."""
        reset_backend_metadata_provider()

        p1 = get_backend_metadata_provider(["aer"])
        p2 = get_backend_metadata_provider(["aer", "custatevec"])

        # Should be the same instance
        assert p1 is p2

        # Should use first call's executors
        assert p1.available_executors == ["aer"]

    def test_provider_reset(self) -> None:
        """Test that reset allows new configuration."""
        reset_backend_metadata_provider()

        p1 = get_backend_metadata_provider(["aer"])
        assert p1.available_executors == ["aer"]

        reset_backend_metadata_provider()

        p2 = get_backend_metadata_provider(["custatevec"])
        assert p2.available_executors == ["custatevec"]
        assert p1 is not p2

    def test_provider_default_executor(self) -> None:
        """Test that default executor is 'aer'."""
        reset_backend_metadata_provider()

        provider = get_backend_metadata_provider()
        assert provider.available_executors == ["aer"]
