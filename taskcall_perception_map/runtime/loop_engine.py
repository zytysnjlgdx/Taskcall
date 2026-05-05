"""节点内部自主循环。

这是这套骨架里最接近 Claude Code “对话运转核心”的地方。

它的关键思想不是“让模型直接干活”，而是把职责拆开：
- adapter 负责决定下一步想做什么
- loop engine 负责真正执行这一步，并统一处理
  - 权限校验
  - capability 调用
  - transcript 记录
  - 输出校验
  - 失败收口

所以这个文件本质上是节点级别的中控器。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from taskcall_perception_map.capabilities.base import CapabilityInvocationContext
from taskcall_perception_map.capabilities.permission_gate import PermissionGate
from taskcall_perception_map.capabilities.registry import CapabilityRegistry
from taskcall_perception_map.domain.models import (
    AdapterScratchpad,
    AgentStepRequest,
    CapabilityCallStep,
    CompleteStep,
    ContinueStep,
    FailStep,
    NodeExecutionResult,
    RuntimeTaskPackage,
    SpawnAgentStep,
    TranscriptEntry,
)
from taskcall_perception_map.runtime.adapter import AgentAdapter
from taskcall_perception_map.runtime.output_validator import OutputValidator
from taskcall_perception_map.storage.transcript_store import InMemoryTranscriptStore

if TYPE_CHECKING:
    from taskcall_perception_map.agents.runtime import ChildAgentRuntime


class LoopEngine:
    """驱动单个节点一直跑到成功、失败或超出轮数限制。"""

    def __init__(
        self,
        *,
        capability_registry: CapabilityRegistry,
        permission_gate: PermissionGate,
        output_validator: OutputValidator,
        transcript_store: InMemoryTranscriptStore,
        child_agent_runtime: ChildAgentRuntime | None = None,
        max_iterations: int = 6,
    ) -> None:
        self.capability_registry = capability_registry
        self.permission_gate = permission_gate
        self.output_validator = output_validator
        self.transcript_store = transcript_store
        self.child_agent_runtime = child_agent_runtime
        self.max_iterations = max_iterations

    async def run(
        self,
        *,
        task_package: RuntimeTaskPackage,
        adapter: AgentAdapter,
        attempt_count: int,
    ) -> NodeExecutionResult:
        # 每次节点执行都单独创建 transcript 和 scratchpad。
        # transcript 用来留痕，scratchpad 用来跨轮保存临时结果。
        transcript = self.transcript_store.create(task_package.node_id)
        scratchpad = AdapterScratchpad()

        self.transcript_store.append(
            transcript.transcript_id,
            TranscriptEntry(
                kind="info",
                message=f"Starting node {task_package.node_id}.",
                data={
                    "goal": task_package.goal,
                    "agent_profile": task_package.agent_profile,
                    "worker_agent_id": task_package.metadata.get("worker_agent_id"),
                    "worker_agent_name": task_package.metadata.get("worker_agent_name"),
                    "allowed_capabilities": task_package.allowed_capabilities,
                },
            ),
        )

        for iteration in range(1, self.max_iterations + 1):
            # 每一轮都由 adapter 先决定“下一步意图”。
            # 但意图不等于执行本身，真正执行还是由 engine 接管。
            step = await adapter.run_step(
                AgentStepRequest(
                    task_package=task_package,
                    iteration=iteration,
                    transcript_id=transcript.transcript_id,
                    scratchpad=scratchpad,
                )
            )

            if isinstance(step, ContinueStep):
                # ContinueStep 的意思是：
                # “我还没做完，先记一点中间想法，然后继续下一轮。”
                if step.message:
                    scratchpad.notes.append(step.message)
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(kind="model", message=step.message),
                    )
                continue

            if isinstance(step, CapabilityCallStep):
                # 工具/能力调用必须经过 engine，而不是 adapter 自己直接调。
                # 这样权限、日志、异常处理才能保持统一。
                self.permission_gate.assert_allowed(
                    step.capability_name,
                    task_package.allowed_capabilities,
                )
                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(
                        kind="capability",
                        message=f"Invoking capability {step.capability_name}.",
                        data=step.payload,
                    ),
                )
                try:
                    output = await self.capability_registry.invoke(
                        step.capability_name,
                        step.payload,
                        CapabilityInvocationContext(
                            session_id=task_package.session_id,
                            node_id=task_package.node_id,
                            attempt_count=attempt_count,
                            transcript_id=transcript.transcript_id,
                        ),
                    )
                except Exception as exc:  # noqa: BLE001
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(
                            kind="error",
                            message=f"Capability {step.capability_name} failed.",
                            data={"error": str(exc)},
                        ),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=[],
                        transcript_id=transcript.transcript_id,
                        failure_reason=str(exc),
                        retryable=False,
                    )

                # 能力返回值会写进 scratchpad，供后续轮次继续使用。
                # save_as 可以理解为这次工具结果在节点内部的临时变量名。
                save_key = step.save_as or f"{step.capability_name}:{iteration}"
                scratchpad.capability_outputs[save_key] = output
                if step.message:
                    scratchpad.notes.append(step.message)
                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(
                        kind="result",
                        message=f"Capability {step.capability_name} completed.",
                        data={"save_as": save_key, "output": output},
                    ),
                )
                continue

            if isinstance(step, SpawnAgentStep):
                if not step.wait_for_result:
                    reason = "Asynchronous child-agent execution is not supported yet."
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(kind="error", message=reason),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=[],
                        transcript_id=transcript.transcript_id,
                        failure_reason=reason,
                        retryable=False,
                    )

                if self.child_agent_runtime is None:
                    reason = "No child-agent runtime is configured for SpawnAgentStep."
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(kind="error", message=reason),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=[],
                        transcript_id=transcript.transcript_id,
                        failure_reason=reason,
                        retryable=False,
                    )

                save_key = step.save_as or f"agent:{iteration}"
                if step.message:
                    scratchpad.notes.append(step.message)
                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(
                        kind="agent",
                        message=step.message or "Spawning child agent.",
                        data={
                            "save_as": save_key,
                            "requested_agent_type": step.requested_agent_type,
                            "required_capabilities": step.required_capabilities,
                        },
                    ),
                )

                try:
                    child_result = await self.child_agent_runtime.run_child_agent(
                        parent_task_package=task_package,
                        parent_transcript_id=transcript.transcript_id,
                        parent_iteration=iteration,
                        step=step,
                    )
                except Exception as exc:  # noqa: BLE001
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(
                            kind="error",
                            message="Child agent execution failed.",
                            data={"error": str(exc)},
                        ),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=[],
                        transcript_id=transcript.transcript_id,
                        failure_reason=str(exc),
                        retryable=False,
                    )

                if child_result.status != "success":
                    reason = child_result.failure_reason or "Child agent failed."
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(
                            kind="error",
                            message="Child agent finished without success.",
                            data={
                                "child_agent_id": child_result.identity.agent_id,
                                "child_status": child_result.status,
                                "reason": reason,
                            },
                        ),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=[],
                        transcript_id=transcript.transcript_id,
                        failure_reason=reason,
                        retryable=False,
                    )

                scratchpad.agent_outputs[save_key] = child_result
                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(
                        kind="agent",
                        message="Child agent completed.",
                        data={
                            "save_as": save_key,
                            "child_agent_id": child_result.identity.agent_id,
                            "child_agent_name": child_result.identity.display_name,
                            "transcript_id": child_result.transcript_id,
                            "artifacts_count": len(child_result.artifacts),
                        },
                    ),
                )
                continue

            if isinstance(step, CompleteStep):
                # 节点说自己完成了，不代表系统立刻相信。
                # 还要用 OutputValidator 检查它是否真的按契约返回了结果。
                validation = self.output_validator.validate(
                    task_package,
                    step.artifacts,
                )
                if not validation.ok:
                    self.transcript_store.append(
                        transcript.transcript_id,
                        TranscriptEntry(
                            kind="error",
                            message="Output validation failed.",
                            data=[issue.message for issue in validation.issues],
                        ),
                    )
                    return NodeExecutionResult(
                        node_id=task_package.node_id,
                        status="failed",
                        artifacts=step.artifacts,
                        transcript_id=transcript.transcript_id,
                        raw_output=step.raw_output,
                        failure_reason="Output validation failed.",
                        retryable=False,
                        issues=validation.issues,
                    )

                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(
                        kind="result",
                        message=f"Node {task_package.node_id} completed.",
                        data={"artifacts_count": len(step.artifacts)},
                    ),
                )
                return NodeExecutionResult(
                    node_id=task_package.node_id,
                    status="success",
                    artifacts=step.artifacts,
                    transcript_id=transcript.transcript_id,
                    raw_output=step.raw_output,
                )

            if isinstance(step, FailStep):
                # FailStep 是 adapter 主动声明：
                # “这条路走不通了，这个节点到此为止。”
                self.transcript_store.append(
                    transcript.transcript_id,
                    TranscriptEntry(kind="error", message=step.reason),
                )
                return NodeExecutionResult(
                    node_id=task_package.node_id,
                    status="failed",
                    artifacts=[],
                    transcript_id=transcript.transcript_id,
                    failure_reason=step.reason,
                    retryable=step.retryable,
                )

        # 超过最大轮数仍未完成，说明这个节点陷入了无结果循环。
        # 这里直接收口失败，防止无限跑下去。
        self.transcript_store.append(
            transcript.transcript_id,
            TranscriptEntry(
                kind="error",
                message="Loop engine exhausted max iterations.",
            ),
        )
        return NodeExecutionResult(
            node_id=task_package.node_id,
            status="failed",
            artifacts=[],
            transcript_id=transcript.transcript_id,
            failure_reason="Loop engine exhausted max iterations.",
            retryable=False,
        )
