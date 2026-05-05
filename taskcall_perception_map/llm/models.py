"""Shared request/response objects for provider-agnostic LLM calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


LLMMessageRole = Literal["system", "user", "assistant"]
LLMResponseFormat = Literal["text", "json"]


@dataclass(slots=True)
class LLMMessage:
    """One chat-style message passed to a language model."""

    role: LLMMessageRole
    content: str


@dataclass(slots=True)
class LLMRequest:
    """Normalized generation request understood by all providers."""

    messages: list[LLMMessage]
    model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2_000
    response_format: LLMResponseFormat = "text"
    stop_sequences: list[str] = field(default_factory=list)
    provider_params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LLMUsage:
    """Token accounting returned by the provider when available."""

    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(slots=True)
class LLMResponse:
    """Normalized provider response returned to planner/runtime callers."""

    content: str
    raw: Any | None = None
    finish_reason: str | None = None
    usage: LLMUsage | None = None
