"""Project-specific exceptions."""


class ConfigurationError(ValueError):
    """Raised when local configuration violates the safe configuration contract."""


class ReleaseIncompleteError(ValueError):
    """Raised when a release fails completeness checks and cannot be completed."""


class ReleaseImmutableError(ReleaseIncompleteError):
    """Raised before attempting to replace a completed release."""
