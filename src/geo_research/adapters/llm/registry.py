"""Explicit LLM adapter registry."""

from geo_research.adapters.llm.base import LLMAdapter
from geo_research.adapters.llm.chatgpt import ChatGPTAdapter
from geo_research.adapters.llm.gemini import GeminiAdapter

LLM_ADAPTERS: dict[str, LLMAdapter] = {
    "chatgpt": ChatGPTAdapter(),
    "gemini": GeminiAdapter(),
}
