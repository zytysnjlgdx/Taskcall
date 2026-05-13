from __future__ import annotations

from typing import Any, cast

from taskcall_perception_map.domain.models import (
    ArtifactSelector,
    ArtifactType,
    OutputSpec,
    PlanGraph,
    PlanNode,
)
from taskcall_perception_map.planner.instructions import (
    NORMAL_EXECUTION_INSTRUCTION,
    VALIDATION_EXECUTION_INSTRUCTION,
    VALIDATION_EXPECTED_OUTPUTS,
)


VALID_ARTIFACT_TYPES = {
    "value",
    "evidence",
    "rule",
    "candidate",
    "judgement",
    "code",
    "other",
}


def convert_task_topology_schema_to_plan_graph(decomposition: dict[str, Any]) -> PlanGraph:
    """
    将 task_topology 的分解结果（LLM 输出的 dict）转换为框架的 PlanGraph 对象。

    输入 (decomposition dict，即 LLM 返回的 JSON 解析后的 dict):
        question_text                    : str   - 原始问题文本
        final_answer_subproblem_id       : str   - 产出最终答案的子问题 id
        validation_subproblem_ids        : list  - 验证子问题 id 列表
        subproblems (或 nodes)           : list  - 子问题列表，每个元素包含:
            id                           : str   - 子问题唯一标识
            goal                         : str   - 子目标
            evidence_from_question       : list  - 从原题中提取的证据
            inputs_from_subproblems      : list  - 上游输入引用，每项包含:
                source_subproblem_id     : str   - 上游子问题 id（兼容 source_node_id）
                field                    : str   - 要取的字段名
            outputs                      : list  - 输出契约，每项包含:
                field                    : str   - 输出字段名
                type                     : str   - 产物类型（兼容 artifact_type）
                description              : str   - 字段说明
            depends_on                   : list  - 依赖的上游子问题 id 列表

    输出 (PlanGraph 对象):
        question_text                    : str   - 原始问题文本
        nodes                            : list  - PlanNode 列表
        metadata                         : dict  - 包含 final_answer_node_id 和 validation_node_ids

    字段映射关系:
        subproblems                      → PlanGraph.nodes
        final_answer_subproblem_id       → metadata["final_answer_node_id"]
        validation_subproblem_ids        → metadata["validation_node_ids"]
        inputs[].source_subproblem_id    → ArtifactSelector.source_node_id
        outputs[].type                   → OutputSpec.artifact_type
    """

    question_text = str(decomposition.get("question_text", "")).strip()

    raw_subproblems = decomposition.get("subproblems")
    if raw_subproblems is None:
        raw_subproblems = decomposition.get("nodes", [])

    if not isinstance(raw_subproblems, list):
        raise ValueError("decomposition['subproblems'] or decomposition['nodes'] must be a list.")

    if len(raw_subproblems) == 0:
        raise ValueError("decomposition['subproblems'] or decomposition['nodes'] must contain at least one subproblem.")

    final_answer_node_id = (
        decomposition.get("final_answer_subproblem_id")
        or decomposition.get("final_answer_node_id")
    )

    if final_answer_node_id is not None:
        if not isinstance(final_answer_node_id, str) or not final_answer_node_id.strip():
            raise ValueError(
                "final_answer_subproblem_id/final_answer_node_id must be a non-empty string."
            )
        final_answer_node_id = final_answer_node_id.strip()

    validation_node_ids = set(
        _str_list(
            decomposition.get(
                "validation_subproblem_ids",
                decomposition.get("validation_node_ids", []),
            )
        )
    )

    if validation_node_ids and not final_answer_node_id:
        raise ValueError(
            "validation_subproblem_ids is not empty, but final_answer_subproblem_id is missing."
        )


    all_node_ids = {
        _required_str(raw_node, "id")
        for raw_node in raw_subproblems
        if isinstance(raw_node, dict)
    }

    unknown_validation_node_ids = validation_node_ids - all_node_ids  # 找出哪些验证节点是不存在的
    if unknown_validation_node_ids:
        raise ValueError(
            f"validation_subproblem_ids contains unknown node ids: "
            f"{sorted(unknown_validation_node_ids)}"
        )

    if final_answer_node_id is not None and final_answer_node_id not in all_node_ids:
        raise ValueError(
            f"final_answer_subproblem_id/final_answer_node_id '{final_answer_node_id}' "
            "does not exist in subproblems/nodes."
        )
    nodes: list[PlanNode] = []

    for index, raw_node in enumerate(raw_subproblems):
        if not isinstance(raw_node, dict):
            raise ValueError("Each subproblem/node must be a dict.")

        node_id = _required_str(raw_node, "id")
        goal = _required_str(raw_node, "goal")
        is_validation_subproblem = node_id in validation_node_ids  # 会返回bool

        evidence_from_question = _str_list(
            raw_node.get("evidence_from_question", raw_node.get("evidence", []))
        )

        previous_nodes = raw_subproblems[:index]

        if is_validation_subproblem:
            previous_node_ids = [
                _required_str(prev_node, "id")
                for prev_node in previous_nodes
                if isinstance(prev_node, dict)
            ]

            if final_answer_node_id not in previous_node_ids:
                raise ValueError(
                    f"{node_id} is a validation node, but final answer node "
                    f"'{final_answer_node_id}' does not appear before it."
                )

            inputs = _build_validation_inputs(previous_nodes)
            outputs = _convert_outputs(VALIDATION_EXPECTED_OUTPUTS)
            depends_on = previous_node_ids
            upstream_dependency_graph = _build_upstream_dependency_graph(previous_nodes)

        else:
            inputs = _convert_inputs(
                raw_node.get(
                    "inputs_from_subproblems",
                    raw_node.get("inputs_from_nodes", raw_node.get("inputs", [])),
                )
            )

            outputs = _convert_outputs(raw_node.get("outputs", []))
            if len(outputs) == 0:
                raise ValueError(f"{node_id}.outputs must contain at least one output spec.")

            depends_on = _str_list(
                raw_node.get("depends_on", raw_node.get("dependencies", []))
            )

            upstream_dependency_graph = []

        # 关键保护：只要使用了某个上游节点的输出，就必须依赖那个节点。
        # 否则 scheduler 可能会提前执行当前节点，导致找不到 upstream_inputs。
        depends_on = _merge_unique(
            depends_on,
            [inp.source_node_id for inp in inputs],
        )
        raw_node_metadata = raw_node.get("metadata") or {}
        if not isinstance(raw_node_metadata, dict):
            raise ValueError(f"{node_id}.metadata must be a dict when present.")
        node_metadata = dict(raw_node_metadata)  # 复制一份raw_node_metadata
        instruction = raw_node.get("instruction")  # 会返回None
        if instruction is not None and not isinstance(instruction, str):
            raise ValueError(f"{node_id}.instruction must be a string when present.")

        if instruction is None:
            if is_validation_subproblem:
                instruction = VALIDATION_EXECUTION_INSTRUCTION
            else:
                instruction = NORMAL_EXECUTION_INSTRUCTION

        node_metadata["is_validation_subproblem"] = is_validation_subproblem
        node_metadata["validation_target_subproblem_id"] = (
            final_answer_node_id if is_validation_subproblem else None
        )
        node_metadata["upstream_dependency_graph"] = upstream_dependency_graph

        nodes.append(
            PlanNode(
                id=node_id,
                goal=goal,
                evidence_from_question=evidence_from_question,
                inputs_from_subproblems=inputs,
                outputs=outputs,
                depends_on=depends_on,
                agent_profile=str(raw_node.get("agent_profile", "general_worker")),
                tool_policy=_str_list(raw_node.get("tool_policy", [])),
                instruction=instruction,
                metadata=node_metadata,
            )
        )

    raw_metadata = decomposition.get("metadata") or {}
    if not isinstance(raw_metadata, dict):
        raise ValueError("decomposition['metadata'] must be a dict when present.")
    metadata = dict(raw_metadata)

    if "final_answer_subproblem_id" in decomposition:
        metadata["final_answer_node_id"] = decomposition["final_answer_subproblem_id"]

    if "final_answer_node_id" in decomposition:
        metadata["final_answer_node_id"] = decomposition["final_answer_node_id"]

    if "validation_subproblem_ids" in decomposition:
        metadata["validation_node_ids"] = decomposition["validation_subproblem_ids"]

    if "validation_node_ids" in decomposition:
        metadata["validation_node_ids"] = decomposition["validation_node_ids"]

    return PlanGraph(
        question_text=question_text,
        nodes=nodes,
        metadata=metadata,
    )


def _convert_inputs(raw_inputs: Any) -> list[ArtifactSelector]:
    if raw_inputs is None:
        return []

    if not isinstance(raw_inputs, list):
        raise ValueError("inputs_from_subproblems must be a list.")

    inputs: list[ArtifactSelector] = []

    for item in raw_inputs:  # item表示其中一个输入
        if not isinstance(item, dict):
            raise ValueError("Each input selector must be a dict.")

        source_node_id = (
            item.get("source_node_id")
            or item.get("source_subproblem_id")
            or item.get("source")
        )

        if not isinstance(source_node_id, str) or not source_node_id.strip():
            raise ValueError("Input selector must contain source_node_id or source_subproblem_id.")

        field = item.get("field")
        if not isinstance(field, str) or not field.strip():
            raise ValueError("Input selector must contain non-empty field.")

        required = item.get("required", True)
        if not isinstance(required, bool):
            required = True

        inputs.append(
            ArtifactSelector(
                source_node_id=source_node_id.strip(),
                field=field.strip(),
                required=required,
            )
        )

    return inputs


def _convert_outputs(raw_outputs: Any) -> list[OutputSpec]:
    if raw_outputs is None:
        return []

    if not isinstance(raw_outputs, list):
        raise ValueError("outputs must be a list.")

    outputs: list[OutputSpec] = []

    for item in raw_outputs:  # item表示其中一个输出
        if not isinstance(item, dict):
            raise ValueError("Each output spec must be a dict.")

        field = _required_str(item, "field")
        description = str(item.get("description", field)).strip()

        artifact_type = (
            item.get("artifact_type")
            or item.get("type")
            or "value"
        )

        if artifact_type not in VALID_ARTIFACT_TYPES:
            artifact_type = "other"

        required = item.get("required", True)
        if not isinstance(required, bool):
            required = True

        outputs.append(
            OutputSpec(
                field=field,
                artifact_type=cast(ArtifactType, artifact_type),
                description=description,
                required=required,
            )
        )

    return outputs


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Required field '{key}' must be a non-empty string.")
    return value.strip()


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []

    if not isinstance(value, list):
        return []

    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())

    return result


def _merge_unique(first: list[str], second: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for item in first + second:
        if item not in seen:
            result.append(item)
            seen.add(item)

    return result

def _build_validation_inputs(raw_nodes: list[Any]) -> list[ArtifactSelector]:
    """
    为验证节点构建输入契约：把所有上游节点的全部 outputs 都作为验证节点的输入。

    验证节点需要看到所有上游节点的结果才能做判断，所以不需要手动指定 inputs，
    而是自动把前面每个节点的每个 output 都收进来。

    输入:
        raw_nodes: 验证节点之前的所有上游节点（原始 dict 列表）

    输出:
        list[ArtifactSelector]: 验证节点的输入契约列表，每项引用一个上游节点的某个 output
    """
    inputs: list[ArtifactSelector] = []

    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("Each upstream subproblem/node must be a dict.")

        source_node_id = _required_str(raw_node, "id")

        raw_outputs = raw_node.get("outputs", [])
        if not isinstance(raw_outputs, list):
            raise ValueError(f"{source_node_id}.outputs must be a list.")

        for output in raw_outputs:
            if not isinstance(output, dict):
                raise ValueError(f"Each output spec of {source_node_id} must be a dict.")

            field = _required_str(output, "field")

            inputs.append(
                ArtifactSelector(
                    source_node_id=source_node_id,
                    field=field,
                    required=True,
                )
            )

    return inputs


def _build_upstream_dependency_graph(raw_nodes: list[Any]) -> list[dict[str, Any]]:
    """
    为验证节点构建上游依赖图的摘要：记录每个上游节点的 id、goal 和 depends_on。

    验证节点执行时需要了解上游节点之间的依赖关系，才能判断错误来源。
    这个函数把上游节点的结构信息打包成一个轻量的摘要列表。

    输入:
        raw_nodes: 验证节点之前的所有上游节点（原始 dict 列表）

    输出:
        list[dict]: 每项包含:
            - subproblem_id: 节点 id
            - goal: 节点目标
            - depends_on: 该节点依赖的上游节点 id 列表
    """
    graph: list[dict[str, Any]] = []

    for raw_node in raw_nodes:
        if not isinstance(raw_node, dict):
            raise ValueError("Each upstream subproblem/node must be a dict.")

        node_id = _required_str(raw_node, "id")
        goal = _required_str(raw_node, "goal")

        explicit_depends_on = _str_list(
            raw_node.get("depends_on", raw_node.get("dependencies", []))
        )

        raw_inputs = raw_node.get(
            "inputs_from_subproblems",
            raw_node.get("inputs_from_nodes", raw_node.get("inputs", [])),
        )
        input_selectors = _convert_inputs(raw_inputs)
        inferred_depends_on = [inp.source_node_id for inp in input_selectors]

        depends_on = _merge_unique(explicit_depends_on, inferred_depends_on)

        graph.append(
            {
                "subproblem_id": node_id,
                "goal": goal,
                "depends_on": depends_on,
            }
        )

    return graph