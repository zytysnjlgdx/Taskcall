"""Worker-agent protocol for the lightweight delegation layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from taskcall_perception_map.agents.models import WorkerAgentIdentity
from taskcall_perception_map.domain.models import (
    AgentStepRequest,
    CapabilityCallStep,
    CompleteStep,
    ContinueStep,
    FailStep,
    SpawnAgentStep,
)

WorkerAgentStep = (
    ContinueStep | CapabilityCallStep | SpawnAgentStep | CompleteStep | FailStep
)


class StepAdapter(Protocol):
    """Minimal step interface shared by adapters and worker-agents."""

    async def run_step(self, request: AgentStepRequest) -> WorkerAgentStep:
        ...


class WorkerAgent(StepAdapter, Protocol):
    """A node-scoped worker with identity plus the step interface."""

    identity: WorkerAgentIdentity

    async def run_step(self, request: AgentStepRequest) -> WorkerAgentStep:
        ...


@dataclass(slots=True)
class AdapterBackedWorkerAgent:
    """Wrap an existing adapter so it behaves like an explicit worker-agent."""

    identity: WorkerAgentIdentity
    adapter: StepAdapter

    async def run_step(self, request: AgentStepRequest) -> WorkerAgentStep:
        return await self.adapter.run_step(request)
