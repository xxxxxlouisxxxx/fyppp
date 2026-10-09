from __future__ import annotations

from pathlib import Path

from geo_research.transforms.llm_raw import transform_llm_raw_file


def test_transform_llm_raw_file_extracts_structured_results() -> None:
    raw_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures" / "llm" / "gemini_response.json"
    )

    result = transform_llm_raw_file(raw_path)

    assert result["provider"] == "dataforseo"
    assert result["platform"] == "gemini"
    assert result["query"] == "Which resale platforms are safest for buying sneakers?"
    assert result["task_id"] == "09280424-2476-0626-0000-2721c3e60279"
    assert result["result_count"] == 11
    assert result["items"][0]["rank_absolute"] == 1
    assert result["items"][0]["item_type"] == "gemini_text"
    assert result["citations"][0]["domain"] == "whop.com"
    assert result["citations"][0]["url"].startswith("https://whop.com/")
