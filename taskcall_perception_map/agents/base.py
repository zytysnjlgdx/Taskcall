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
    """
    WorkerAgent 的具体实现：给已有的 adapter 包上一层 agent 身份。

    作用：adapter 只有执行能力（run_step），没有身份信息。
         AdapterBackedWorkerAgent 在 adapter 外面套了一个 WorkerAgentIdentity，
         让它同时具备身份 + 执行能力，满足 WorkerAgent 接口要求。

    字段:
        identity: agent 身份信息（id、所属 session、对应节点等）
        adapter:  实际执行逻辑的 StepAdapter（你同学负责的执行层）
    """

    identity: WorkerAgentIdentity
    adapter: StepAdapter

    async def run_step(self, request: AgentStepRequest) -> WorkerAgentStep:
        """
        执行一个步骤：直接委托给内部的 adapter。

        输入:
            request: agent 步骤请求（AgentStepRequest）

        输出:
            WorkerAgentStep: 执行结果（ContinueStep/CompleteStep/FailStep 等）
        """
        return await self.adapter.run_step(request)
