"""Route planner/worker calls to the right LLM client instance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from taskcall_perception_map.llm.base import LLMClient
from taskcall_perception_map.llm.config import LLMRouteConfig, LLMRouteName
from taskcall_perception_map.llm.models import LLMRequest, LLMResponse


class LLMRouter:
    """Simple role-based client router for planner/runtime consumers."""

    def __init__(
        self,
        *,
        default_client: LLMClient,
        named_clients: Mapping[str, LLMClient] | None = None,
        route_config: LLMRouteConfig | None = None,
    ) -> None:
        self.default_client = default_client
        self.named_clients = dict(named_clients or {})
        self.route_config = route_config

    def get_client(self, route: LLMRouteName = "default") -> LLMClient:
        return self.named_clients.get(route, self.default_client)

    def resolve_request(
        self,
        request: LLMRequest,
        *,
        route: LLMRouteName = "default",
    ) -> LLMRequest:
        """Fill route-level defaults before handing the request to a client."""
        if request.model:
            return request
        if self.route_config is None:
            return request

        routed_model = self.route_config.model_for(route)
        if not routed_model:
            return request
        return replace(request, model=routed_model)

    async def generate(
        self,
        request: LLMRequest,
        *,
        route: LLMRouteName = "default",
    ) -> LLMResponse:
        client = self.get_client(route)
        resolved_request = self.resolve_request(request, route=route)
        return await client.generate(resolved_request)
