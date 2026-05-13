"""Configuration objects for LLM providers and model routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


LLMRouteName = Literal["default", "planner", "worker", "verifier"]


@dataclass(slots=True)
class LLMProviderConfig:
    """Connection settings for one concrete provider backend."""

    provider: str
    base_url: str
    api_key: str
    default_model: str
    timeout_seconds: float = 60.0
    extra_headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class LLMRouteConfig:
    """Optional per-role model overrides on top of provider defaults."""

    planner_model: str | None = None
    worker_model: str | None = None
    verifier_model: str | None = None

    def model_for(self, route: LLMRouteName) -> str | None:
        if route == "planner":
            return self.planner_model
        if route == "worker":
            return self.worker_model
        if route == "verifier":
            return self.verifier_model
        return None
