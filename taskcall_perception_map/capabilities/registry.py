"""Registry for looking up and invoking named capabilities."""

from __future__ import annotations

from typing import Any

from taskcall_perception_map.capabilities.base import (
    Capability,
    CapabilityInvocationContext,
)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        """Expose a capability to the runtime under its declared name."""
        self._capabilities[capability.name] = capability

    def get(self, capability_name: str) -> Capability | None:
        """Return the capability if it is registered, else None."""
        return self._capabilities.get(capability_name)

    async def invoke(
        self,
        capability_name: str,
        payload: Any,
        context: CapabilityInvocationContext,
    ) -> Any:
        """Resolve a capability and delegate the actual work to it."""
        capability = self.get(capability_name)
        if capability is None:
            raise KeyError(f"Unknown capability: {capability_name}")
        return await capability.invoke(payload, context)
