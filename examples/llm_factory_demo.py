from __future__ import annotations

from taskcall_perception_map import (
    LLMMessage,
    LLMProviderConfig,
    LLMRequest,
    LLMRouteConfig,
    build_openai_compatible_router,
)


def describe_route(router, route: str) -> None:  # type: ignore[no-untyped-def]
    client = router.get_client(route)  # type: ignore[arg-type]
    resolved = router.resolve_request(
        LLMRequest(messages=[LLMMessage(role="user", content="hello")]),
        route=route,  # type: ignore[arg-type]
    )
    print(
        f"{route:<8} -> client_base_url={client.config.base_url}, "
        f"resolved_model={resolved.model}"
    )


def main() -> None:
    default_provider = LLMProviderConfig(
        provider="openai_compatible",
        base_url="https://worker.example.com/v1",
        api_key="worker-key",
        default_model="worker-default",
    )
    planner_provider = LLMProviderConfig(
        provider="openai_compatible",
        base_url="https://planner.example.com/v1",
        api_key="planner-key",
        default_model="planner-default",
    )
    route_config = LLMRouteConfig(
        planner_model="planner-model-x",
        worker_model="worker-model-y",
        verifier_model="verifier-model-z",
    )

    router = build_openai_compatible_router(
        provider_config=default_provider,
        route_config=route_config,
        named_provider_configs={"planner": planner_provider},
    )

    print("Route -> client/model mapping")
    describe_route(router, "planner")
    describe_route(router, "worker")
    describe_route(router, "verifier")
    describe_route(router, "default")

    manual_request = LLMRequest(
        model="manual-override",
        messages=[LLMMessage(role="user", content="use my explicit model")],
    )
    manual_resolved = router.resolve_request(manual_request, route="planner")
    print()
    print("Manual override test")
    print(
        "planner  -> "
        f"request_model={manual_request.model}, "
        f"resolved_model={manual_resolved.model}"
    )


if __name__ == "__main__":
    main()
