from __future__ import annotations

import importlib

import httpx


def test_package_imports_without_http_calls(monkeypatch) -> None:
    def fail_on_http(*args: object, **kwargs: object) -> None:
        raise AssertionError("HTTP calls during import are prohibited")

    monkeypatch.setattr(httpx, "request", fail_on_http)
    monkeypatch.setattr(httpx.Client, "request", fail_on_http)
    monkeypatch.setattr(httpx.AsyncClient, "request", fail_on_http)

    package = importlib.reload(importlib.import_module("geo_research"))
    config = importlib.reload(importlib.import_module("geo_research.config.settings"))

    assert package.__version__
    assert config.Settings
