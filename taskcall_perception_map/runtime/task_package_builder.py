"""把计划节点组装成运行时任务包。

它的作用很像“执行前装配器”：
- 从 plan node 里拿静态定义
- 从 artifact store 里拿上游输入
- 拼成一个 adapter 能直接消费的 RuntimeTaskPackage
"""

from __future__ import annotations

from taskcall_perception_map.domain.models import PlanNode, RuntimeTaskPackage
from taskcall_perception_map.storage.artifact_store import InMemoryArtifactStore


class MissingArtifactsError(RuntimeError):
    """节点缺少必需上游输入时抛出的错误。"""

    pass


class TaskPackageBuilder:
    """把静态 PlanNode 翻译成可执行的 RuntimeTaskPackage。"""

    def build(
        self,
        *,
        session_id: str,
        question_text: str,
        node: PlanNode,
        artifact_store: InMemoryArtifactStore,
    ) -> RuntimeTaskPackage:
        # 节点执行之前，先把它声明要用的上游输入都解析出来。
        resolved_inputs = artifact_store.resolve_inputs(node.inputs_from_subproblems)
        if resolved_inputs.missing:
            missing_fields = ", ".join(
                f"{item.source_node_id}.{item.field}"
                for item in resolved_inputs.missing
            )
            raise MissingArtifactsError(
                f"Node {node.id} is missing required upstream inputs: {missing_fields}"
            )

        # planner 没有提供自定义 instruction 时，runtime 会补一条默认指令，
        # 重点提醒节点按 expected outputs 返回结构化结果。
        instruction = node.instruction or (
            f"Complete node {node.id}: {node.goal}. "
            "Return structured artifacts that match the expected outputs."
        )

        return RuntimeTaskPackage(
            session_id=session_id,
            question_text=question_text,
            node_id=node.id,
            goal=node.goal,
            agent_profile=node.agent_profile,
            local_evidence=list(node.evidence_from_question),
            upstream_inputs=resolved_inputs.artifacts,
            expected_outputs=list(node.outputs),
            instruction=instruction,
            # allowed_capabilities=list(node.tool_policy),
            metadata=dict(node.metadata),
        )
