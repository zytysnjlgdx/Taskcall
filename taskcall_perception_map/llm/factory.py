"""Assembly helpers for constructing LLM clients and routers."""

from __future__ import annotations

from collections.abc import Mapping

from taskcall_perception_map.llm.config import (
    LLMProviderConfig,
    LLMRouteConfig,
    LLMRouteName,
)
from taskcall_perception_map.llm.providers.openai_compatible import (
    OpenAICompatibleClient,
)
from taskcall_perception_map.llm.router import LLMRouter


def build_openai_compatible_client(
    provider_config: LLMProviderConfig,
) -> OpenAICompatibleClient:
    """Build one OpenAI-compatible client from provider settings."""
    return OpenAICompatibleClient(config=provider_config)


def build_openai_compatible_router(
    *,
    provider_config: LLMProviderConfig,
    route_config: LLMRouteConfig | None = None,
    named_provider_configs: Mapping[LLMRouteName, LLMProviderConfig] | None = None,
) -> LLMRouter:
    """Build a router with one default client plus optional route-specific ones.

    Typical use:
    - one provider config shared by all routes
    - route_config controls which model each route prefers

    Advanced use:
    - pass named_provider_configs to give planner/worker/verifier different
      provider backends while still keeping route-level model overrides.
    """

    default_client = build_openai_compatible_client(provider_config)
    named_clients = {
        route: build_openai_compatible_client(config)
        for route, config in (named_provider_configs or {}).items()
    }
    return LLMRouter(
        default_client=default_client,
        named_clients=named_clients,
        route_config=route_config,
    )
