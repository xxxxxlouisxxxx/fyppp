"""Explicit SERP adapter registry."""

from geo_research.adapters.serp.baidu import BaiduOrganicAdapter
from geo_research.adapters.serp.base import SERPAdapter
from geo_research.adapters.serp.bing import BingOrganicAdapter
from geo_research.adapters.serp.google import GoogleOrganicAdapter
from geo_research.adapters.serp.yahoo import YahooOrganicAdapter

SERP_ADAPTERS: dict[str, SERPAdapter] = {
    "baidu": BaiduOrganicAdapter(),
    "google": GoogleOrganicAdapter(),
    "bing": BingOrganicAdapter(),
    "yahoo": YahooOrganicAdapter(),
}
