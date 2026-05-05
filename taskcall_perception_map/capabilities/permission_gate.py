"""Minimal policy check for whether a node may use a capability."""

from __future__ import annotations


class PermissionGate:
    def is_allowed(
        self,
        capability_name: str,
        allowed_capabilities: list[str],
    ) -> bool:
        """Return True when the node-level tool policy allows the call."""
        return capability_name in allowed_capabilities

    def assert_allowed(
        self,
        capability_name: str,
        allowed_capabilities: list[str],
    ) -> None:
        """Raise early so adapters cannot bypass node capability policy."""
        if not self.is_allowed(capability_name, allowed_capabilities):
            raise PermissionError(
                f"Capability '{capability_name}' is not allowed for this node."
            )
