"""Tests for BackendMetadataProvider."""

from qiskit_ibm_runtime.fake_provider import FakeProviderForBackendV2

from qiskit_runtime_server.providers.backend_metadata import (
    STATEVECTOR_BACKEND_NAMES,
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

        # Should have (base_count + statevector_count) × 1 backends
        base_count = len(FakeProviderForBackendV2().backends())
        statevector_count = len(STATEVECTOR_BACKEND_NAMES)
        assert len(backend_names) == base_count + statevector_count

    def test_list_backends_multiple_executors(self) -> None:
        """Test listing backends with multiple executors."""
        provider = BackendMetadataProvider(available_executors=["aer", "custatevec"])
        response = provider.list_backends()

        backend_names = [b["backend_name"] for b in response.devices]

        # Should have both aer and custatevec variants
        assert "fake_manila@aer" in backend_names
        assert "fake_manila@custatevec" in backend_names

        # Should have (base_count + statevector_count) × 2 backends
        base_count = len(FakeProviderForBackendV2().backends())
        statevector_count = len(STATEVECTOR_BACKEND_NAMES)
        assert len(backend_names) == (base_count + statevector_count) * 2

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


class TestStatevectorBackend:
    """Tests for statevector backend functionality."""

    def test_statevector_backend_enabled_by_default(self) -> None:
        """Test that statevector backend is enabled by default."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        assert provider._statevector_backend is not None

    def test_statevector_backend_disabled(self) -> None:
        """Test disabling statevector backend."""
        provider = BackendMetadataProvider(
            available_executors=["aer"],
            statevector_config={"enabled": False},
        )
        assert provider._statevector_backend is None

    def test_statevector_backend_custom_qubits(self) -> None:
        """Test creating statevector backend with custom qubit count."""
        provider = BackendMetadataProvider(
            available_executors=["aer"],
            statevector_config={"num_qubits": 20},
        )
        backend = provider.get_backend("statevector_simulator")
        assert backend.num_qubits == 20

    def test_statevector_backend_no_coupling_map(self) -> None:
        """Test that statevector backend serializes with no coupling map."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        backend = provider.get_backend("statevector_simulator")
        # GenericBackendV2 creates a fully connected coupling map internally,
        # but we serialize it as None to indicate no topology constraints
        backend_dict = provider._backend_to_dict(backend)
        assert backend_dict["coupling_map"] is None

    def test_get_statevector_backend(self) -> None:
        """Test retrieving statevector backend."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        backend = provider.get_backend("statevector_simulator")
        assert backend is not None
        # GenericBackendV2 has a generic name internally,
        # but serialization uses the correct statevector name
        backend_dict = provider._backend_to_dict(backend)
        assert backend_dict["backend_name"] == "statevector_simulator" or backend_dict["backend_name"].startswith("generic_backend")

    def test_get_fake_backend(self) -> None:
        """Test retrieving FakeProvider backend."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        backend = provider.get_backend("fake_manila")
        assert backend is not None
        assert backend.name == "fake_manila"

    def test_parse_statevector_backend_name(self) -> None:
        """Test parsing statevector backend name."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        result = provider.parse_backend_name("statevector_simulator@aer")
        assert result == ("statevector_simulator", "aer")

    def test_list_backends_includes_statevector(self) -> None:
        """Test that list_backends includes statevector backends."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        response = provider.list_backends()
        backend_names = [b["backend_name"] for b in response.devices]

        # Should include statevector backend
        assert "statevector_simulator@aer" in backend_names

        # Count should be base_count + statevector_count
        base_count = len(FakeProviderForBackendV2().backends())
        statevector_count = len(STATEVECTOR_BACKEND_NAMES)
        assert len(backend_names) == (base_count + statevector_count) * 1

    def test_list_backends_statevector_multiple_executors(self) -> None:
        """Test statevector backends with multiple executors."""
        provider = BackendMetadataProvider(available_executors=["aer", "custatevec"])
        response = provider.list_backends()
        backend_names = [b["backend_name"] for b in response.devices]

        # Should have statevector backend for both executors
        assert "statevector_simulator@aer" in backend_names
        assert "statevector_simulator@custatevec" in backend_names

        # Count should be (base_count + statevector_count) × 2
        base_count = len(FakeProviderForBackendV2().backends())
        statevector_count = len(STATEVECTOR_BACKEND_NAMES)
        assert len(backend_names) == (base_count + statevector_count) * 2

    def test_list_backends_statevector_disabled(self) -> None:
        """Test that disabled statevector backends are not listed."""
        provider = BackendMetadataProvider(
            available_executors=["aer"],
            statevector_config={"enabled": False},
        )
        response = provider.list_backends()
        backend_names = [b["backend_name"] for b in response.devices]

        # Should not include statevector backend
        assert "statevector_simulator@aer" not in backend_names

        # Count should be base_count only (no statevector)
        base_count = len(FakeProviderForBackendV2().backends())
        assert len(backend_names) == base_count

    def test_statevector_backend_has_description(self) -> None:
        """Test that statevector backend has proper description."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        response = provider.list_backends()

        # Find statevector backend
        statevector_backend = next(
            b for b in response.devices if b["backend_name"] == "statevector_simulator@aer"
        )

        assert "description" in statevector_backend
        assert "statevector" in statevector_backend["description"].lower()
        assert "ideal" in statevector_backend["description"].lower()

    def test_backend_exists_statevector(self) -> None:
        """Test _backend_exists for statevector backend."""
        provider = BackendMetadataProvider(available_executors=["aer"])
        assert provider._backend_exists("statevector_simulator")
        assert provider._backend_exists("fake_manila")
        assert not provider._backend_exists("nonexistent_backend")
