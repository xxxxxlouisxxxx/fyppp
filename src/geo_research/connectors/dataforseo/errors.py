"""Safe, typed DataForSEO contract errors."""

from __future__ import annotations


class DataForSEOError(RuntimeError):
    """Base class for provider transport contract failures."""


class CapabilityNotVerifiedError(DataForSEOError):
    """Raised when an adapter lacks the official evidence needed to execute."""


class DataForSEOHTTPError(DataForSEOError):
    """An HTTP-layer failure with a provider-independent status classification."""

    def __init__(self, status_code: int, correlation_id: str) -> None:
        self.status_code = status_code
        self.correlation_id = correlation_id
        super().__init__(
            f"DataForSEO HTTP {status_code}; correlation_id={correlation_id}"
        )


class DataForSEOTimeoutError(DataForSEOError):
    """A connect or read timeout."""


class DataForSEOResponseError(DataForSEOError):
    """A response that violates the safe envelope/size/content-type contract."""
