"""Adapter protocol for node-specific reasoning behavior.

The loop engine owns the control flow. Adapters only decide what the
next step should be for the current node.
"""

from __future__ import annotations

from typing import Protocol

from taskcall_perception_map.domain.models import (
    AgentStepRequest,
    CapabilityCallStep,
    CompleteStep,
    ContinueStep,
    FailStep,
    SpawnAgentStep,
)

AgentStepResponse = (
    ContinueStep | CapabilityCallStep | SpawnAgentStep | CompleteStep | FailStep
)


class AgentAdapter(Protocol):
    """Return the next action for the loop engine to execute."""

    async def run_step(self, request: AgentStepRequest) -> AgentStepResponse:
        ...
