"""Injected-transport DataForSEO client with no automatic retries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import uuid4

import httpx

from geo_research.connectors.dataforseo.auth import DataForSEOCredentials
from geo_research.connectors.dataforseo.envelope import ProviderEnvelope, parse_envelope
from geo_research.connectors.dataforseo.errors import (
    DataForSEOHTTPError,
    DataForSEOResponseError,
    DataForSEOTimeoutError,
)
from geo_research.logging_config import configure_logging

_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_PROVIDER_REQUEST_ID_HEADERS = ("x-request-id", "x-provider-request-id")


class DataForSEOClient:
    """Low-level HTTP client that requires a caller-injected transport."""

    def __init__(
        self,
        credentials: DataForSEOCredentials,
        transport: httpx.Client,
        *,
        connect_timeout_seconds: float = 10.0,
        read_timeout_seconds: float = 30.0,
        max_response_bytes: int = _MAX_RESPONSE_BYTES,
    ) -> None:
        self._credentials = credentials
        self._transport = transport
        self._timeout = httpx.Timeout(
            connect=connect_timeout_seconds,
            read=read_timeout_seconds,
            write=read_timeout_seconds,
            pool=connect_timeout_seconds,
        )
        self._max_response_bytes = max_response_bytes
        self._logger = configure_logging("geo_research.dataforseo")

    def request(
        self,
        method: str,
        url: str,
        payload: Mapping[str, object] | Sequence[Mapping[str, object]] | None = None,
        *,
        correlation_id: str | None = None,
    ) -> ProviderEnvelope:
        """Perform one injected-transport JSON request.

        Retries belong above this layer.
        """
        request_id = correlation_id or str(uuid4())
        headers = {
            "Authorization": self._credentials.authorization_header(),
            "X-Request-ID": request_id,
            "Accept": "application/json",
        }
        self._logger.info(
            "DataForSEO request method=%s url=%s correlation_id=%s",
            method,
            url,
            request_id,
        )
        try:
            response = self._transport.request(
                method,
                url,
                json=(
                    [dict(task) for task in payload]
                    if isinstance(payload, Sequence)
                    else dict(payload)
                    if payload is not None
                    else None
                ),
                headers=headers,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            raise DataForSEOTimeoutError(
                f"DataForSEO timeout; correlation_id={request_id}"
            ) from error
        except httpx.HTTPError as error:
            raise DataForSEOResponseError(
                f"DataForSEO transport error; correlation_id={request_id}"
            ) from error
        if response.status_code >= 400:
            raise DataForSEOHTTPError(response.status_code, request_id)
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.casefold():
            raise DataForSEOResponseError(
                f"Expected JSON response; correlation_id={request_id}"
            )
        if len(response.content) > self._max_response_bytes:
            raise DataForSEOResponseError(
                f"Response exceeds size limit; correlation_id={request_id}"
            )
        try:
            payload_data = response.json()
        except ValueError as error:
            raise DataForSEOResponseError(
                f"Invalid JSON response; correlation_id={request_id}"
            ) from error
        provider_request_id = next(
            (
                response.headers.get(header)
                for header in _PROVIDER_REQUEST_ID_HEADERS
                if response.headers.get(header)
            ),
            None,
        )
        return parse_envelope(payload_data, request_id, provider_request_id)
