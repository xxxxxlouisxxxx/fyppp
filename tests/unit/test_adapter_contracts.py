from __future__ import annotations

import pytest

from geo_research.adapters.llm.chatgpt import ChatGPTAdapter
from geo_research.adapters.llm.gemini import GeminiAdapter
from geo_research.adapters.llm.registry import LLM_ADAPTERS
from geo_research.adapters.serp.baidu import BaiduOrganicAdapter
from geo_research.adapters.serp.bing import BingOrganicAdapter
from geo_research.adapters.serp.google import GoogleOrganicAdapter
from geo_research.adapters.serp.registry import SERP_ADAPTERS
from geo_research.adapters.serp.yahoo import YahooOrganicAdapter
from geo_research.connectors.dataforseo.errors import CapabilityNotVerifiedError
from geo_research.domain.llm import LLMPrompt, LLMTarget
from geo_research.domain.serp import Query, SearchTarget


def query() -> Query:
    return Query(
        query_id="query-1",
        keyword="example",
        language="en",
        market="US",
        active=True,
    )


def target(engine: str) -> SearchTarget:
    return SearchTarget(
        search_target_id=f"{engine}-1",
        provider="dataforseo",
        search_engine=engine,
        search_type="organic",
        retrieval_method="TO_BE_VERIFIED",
        location_code="2840",
        language_code="en",
        device="desktop",
        operating_system="windows",
        depth=10,
        active=True,
    )


def prompt() -> LLMPrompt:
    return LLMPrompt(
        prompt_id="prompt-1",
        prompt_text="Example?",
        language="en",
        market="US",
        active=True,
    )


def llm_target(platform: str) -> LLMTarget:
    return LLMTarget(
        llm_target_id=f"{platform}-1",
        provider="dataforseo",
        platform=platform,
        model_name="TO_BE_VERIFIED",
        endpoint_name="TO_BE_VERIFIED",
        location_code="2840",
        language_code="en",
        active=True,
    )


@pytest.mark.parametrize(
    ("adapter", "engine", "language_code"),
    [
        (BingOrganicAdapter(), "bing", "en"),
        (YahooOrganicAdapter(), "yahoo", "en"),
        (BaiduOrganicAdapter(), "baidu", "zh_CN"),
    ],
)
def test_standard_serp_adapters_build_engine_specific_task_post_payloads(
    adapter, engine: str, language_code: str
) -> None:
    standard_target = target(engine).model_copy(
        update={
            "retrieval_method": "standard",
            "language_code": "zh-CN" if engine == "baidu" else "en",
        }
    )

    request = adapter.build_payload(query(), standard_target)

    assert adapter.capability.capability_key == f"serp.{engine}.organic"
    assert adapter.capability.capability_state == "verified"
    assert request.endpoint.endswith(f"/serp/{engine}/organic/task_post")
    assert request.payload == [
        {
            "keyword": "example",
            "location_code": 2840,
            "language_code": language_code,
            "device": "desktop",
            "depth": 10,
            **({"os": "windows"} if engine == "bing" else {}),
        }
    ]


def test_google_organic_adapter_builds_standard_task_post_payload() -> None:
    adapter = GoogleOrganicAdapter()
    standard_target = target("google").model_copy(
        update={"retrieval_method": "standard"}
    )

    request = adapter.build_payload(query(), standard_target)

    assert request.endpoint.endswith("/serp/google/organic/task_post")
    assert adapter.capability.http_method == "POST"
    assert request.payload == [
        {
            "keyword": "example",
            "location_code": 2840,
            "language_code": "en",
            "device": "desktop",
            "os": "windows",
            "depth": 10,
        }
    ]


@pytest.mark.parametrize(
    ("adapter", "registry_os", "provider_os"),
    [
        (GoogleOrganicAdapter(), "windows", "android"),
        (GoogleOrganicAdapter(), "macOS", "ios"),
        (BingOrganicAdapter(), "windows", "android"),
        (BingOrganicAdapter(), "macOS", "ios"),
    ],
)
def test_google_and_bing_normalize_mobile_operating_systems(
    adapter, registry_os: str, provider_os: str
) -> None:
    mobile_target = target(adapter.search_engine).model_copy(
        update={
            "retrieval_method": "standard",
            "device": "Mobile",
            "operating_system": registry_os,
        }
    )

    request = adapter.build_payload(query(), mobile_target)

    assert request.payload[0]["device"] == "mobile"
    assert request.payload[0]["os"] == provider_os


@pytest.mark.parametrize(
    ("adapter", "platform"),
    [(ChatGPTAdapter(), "chatgpt"), (GeminiAdapter(), "gemini")],
)
def test_llm_adapters_are_isolated_and_refuse_unverified_contracts(
    adapter, platform: str
) -> None:
    assert adapter.capability.capability_key == f"llm.{platform}"
    assert adapter.capability.capability_state == "unverified"
    with pytest.raises(CapabilityNotVerifiedError):
        adapter.build_payload(prompt(), llm_target(platform))


def test_adapter_registries_keep_serp_and_llm_contracts_separate() -> None:
    assert set(SERP_ADAPTERS) == {"baidu", "google", "bing", "yahoo"}
    assert set(LLM_ADAPTERS) == {"chatgpt", "gemini"}
