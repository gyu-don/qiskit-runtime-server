"""Backend metadata provider using FakeProviderForBackendV2."""


class BackendMetadataProvider:
    """
    Provider for backend metadata from FakeProviderForBackendV2.

    This class will be extended in future tasks to support:
    - Parsing 'metadata@executor' backend names
    - Listing virtual backends (metadata x executor combinations)
    """

    def __init__(self) -> None:
        """Initialize the backend metadata provider."""
        # Placeholder for future implementation
        pass


# Global singleton instance
_provider_instance: BackendMetadataProvider | None = None


def get_backend_metadata_provider() -> BackendMetadataProvider:
    """
    Get or create the global BackendMetadataProvider singleton.

    Returns:
        BackendMetadataProvider: The global provider instance.
    """
    global _provider_instance

    if _provider_instance is None:
        _provider_instance = BackendMetadataProvider()

    return _provider_instance
