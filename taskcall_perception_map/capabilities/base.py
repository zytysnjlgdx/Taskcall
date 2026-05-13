"""Capability protocol shared by the loop engine and concrete tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class CapabilityInvocationContext:
    """Execution metadata passed to each capability invocation."""

    session_id: str
    node_id: str
    attempt_count: int
    transcript_id: str


class Capability(Protocol):
    """A side-effecting operation exposed to node adapters by name."""

    name: str
    description: str

    async def invoke(
        self,
        payload: Any,
        context: CapabilityInvocationContext,
    ) -> Any:
        ...
