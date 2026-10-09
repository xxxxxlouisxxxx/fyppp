from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

from geo_research.connectors.dataforseo.auth import DataForSEOCredentials
from geo_research.connectors.dataforseo.client import DataForSEOClient
from geo_research.connectors.dataforseo.errors import (
    DataForSEOHTTPError,
    DataForSEOResponseError,
    DataForSEOTimeoutError,
)


def mock_client(handler) -> DataForSEOClient:
    transport = httpx.MockTransport(handler)
    return DataForSEOClient(
        credentials=DataForSEOCredentials(login="test-login", password="test-password"),
        transport=httpx.Client(transport=transport),
    )


def test_client_generates_basic_auth_and_does_not_log_secret(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        expected = base64.b64encode(b"test-login:test-password").decode()
        assert request.headers["Authorization"] == f"Basic {expected}"
        assert request.headers["X-Request-ID"]
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-request-id": "provider-1"},
            json={"tasks": []},
        )

    client = mock_client(handler)
    with caplog.at_level(logging.INFO, logger="geo_research.dataforseo"):
        result = client.request(
            "POST", "https://mock.invalid/contract", {"value": "safe"}
        )

    assert result.provider_request_id == "provider-1"
    assert "test-login" not in caplog.text
    assert "test-password" not in caplog.text
    assert "Basic " not in caplog.text


def test_client_sends_task_post_payload_as_a_json_array() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/task_post")
        assert json.loads(request.content) == [{"keyword": "example"}]
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"tasks": []},
        )

    result = mock_client(handler).request(
        "POST",
        "https://mock.invalid/v3/serp/google/organic/task_post",
        [{"keyword": "example"}],
    )

    assert result.payload == {"tasks": []}


@pytest.mark.parametrize("status_code", [401, 402, 403, 429, 500, 503])
def test_http_errors_are_classified_without_secret_text(status_code: int) -> None:
    client = mock_client(
        lambda request: httpx.Response(
            status_code,
            headers={"content-type": "application/json"},
            json={"error": "x"},
        )
    )

    with pytest.raises(DataForSEOHTTPError) as error:
        client.request("GET", "https://mock.invalid/contract")

    assert error.value.status_code == status_code
    assert "test-password" not in str(error.value)


def test_timeout_is_classified() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("mock timeout", request=request)

    client = mock_client(handler)

    with pytest.raises(DataForSEOTimeoutError):
        client.request("GET", "https://mock.invalid/contract")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, headers={"content-type": "text/plain"}, text="nope"),
        httpx.Response(200, headers={"content-type": "application/json"}, json=[]),
    ],
)
def test_non_json_and_malformed_envelope_fail(response: httpx.Response) -> None:
    client = mock_client(lambda request: response)

    with pytest.raises(DataForSEOResponseError):
        client.request("GET", "https://mock.invalid/contract")
