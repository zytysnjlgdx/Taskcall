"""Base protocol for provider-agnostic LLM clients."""

from __future__ import annotations

from typing import Protocol

from taskcall_perception_map.llm.models import LLMRequest, LLMResponse


class LLMClient(Protocol):
    """Minimal async interface shared by all model providers."""

    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...
