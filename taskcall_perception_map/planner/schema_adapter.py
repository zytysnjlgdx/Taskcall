from __future__ import annotations

from typing import Any, cast

from taskcall_perception_map.domain.models import (
    ArtifactSelector,
    ArtifactType,
    OutputSpec,
    PlanGraph,
    PlanNode,
)
from taskcall_perception_map.planner.instructions import NORMAL_EXECUTION_INSTRUCTION


VALID_ARTIFACT_TYPES = {
    "value",
    "evidence",
    "rule",
    "candidate",
    "judgement",
    "code",
    "other",
}

VALID_FINAL_ANSWER_FORMATS = {
    "choice_label",
    "number_or_expression",
    "code_block",
}


def convert_task_topology_schema_to_plan_graph(decomposition: dict[str, Any]) -> PlanGraph:
    """
    Convert the new task_topology decomposition schema into Taskcall's PlanGraph.

    New planner schema expected from LLM:
    {
        "final_answer_contract": {
            "format": "choice_label|number_or_expression|code_block",
            "allowed_values": []
        },
        "subproblems": [
            {
                "id": "q1",
                "goal": "...",
                "evidence_from_question": [...],
                "inputs_from_subproblems": [
                    {"source_subproblem_id": "q0", "field": "..."}
                ],
                "outputs": [
                    {"field": "...", "type": "value", "description": "..."}
                ]
            }
        ]
    }

    Important design choices:
    1. The LLM no longer outputs depends_on.
       depends_on is derived from inputs_from_subproblems for scheduler compatibility.
    2. The LLM no longer outputs final_answer_subproblem_id.
       final_answer_node_id is derived as the unique terminal/sink node.
    3. The final node output is forced to one stable field: final_answer.
       final_answer_contract is stored in PlanGraph.metadata and final-node metadata.
    """
    if not isinstance(decomposition, dict):
        raise ValueError("decomposition must be a dict.")

    question_text = str(decomposition.get("question_text", "")).strip()

    raw_subproblems = decomposition.get("subproblems")
    if raw_subproblems is None:
        raw_subproblems = decomposition.get("nodes", [])

    if not isinstance(raw_subproblems, list):
        raise ValueError("decomposition['subproblems'] or decomposition['nodes'] must be a list.")

    if len(raw_subproblems) < 2:
        raise ValueError("decomposition must contain at least 2 subproblems.")

    final_answer_contract = _normalize_final_answer_contract(
        decomposition.get("final_answer_contract")
    )

    subproblem_index = _index_raw_subproblems(raw_subproblems)
    dependency_map = _derive_dependency_map(raw_subproblems, subproblem_index)
    _assert_valid_dag(dependency_map)
    final_answer_node_id = _find_unique_terminal_node_id(dependency_map)

    nodes: list[PlanNode] = []

    for raw_node in raw_subproblems:
        if not isinstance(raw_node, dict):
            raise ValueError("Each subproblem/node must be a dict.")

        node_id = _required_str(raw_node, "id")
        goal = _required_str(raw_node, "goal")
        is_final_node = node_id == final_answer_node_id

        evidence_from_question = _str_list(
            raw_node.get("evidence_from_question", raw_node.get("evidence", []))
        )

        inputs = _convert_inputs(
            raw_node.get(
                "inputs_from_subproblems",
                raw_node.get("inputs_from_nodes", raw_node.get("inputs", [])),
            )
        )

        # Scheduler in Taskcall still consumes PlanNode.depends_on, so we fill it
        # deterministically from the upstream input selectors.
        depends_on = dependency_map[node_id]

        if is_final_node:
            outputs = [
                OutputSpec(
                    field="final_answer",
                    artifact_type="value",
                    description="The final answer requested by the original problem.",
                    required=True,
                )
            ]
        else:
            outputs = _convert_outputs(raw_node.get("outputs", []))
            if len(outputs) == 0:
                raise ValueError(f"{node_id}.outputs must contain at least one output spec.")

        raw_node_metadata = raw_node.get("metadata") or {}
        if not isinstance(raw_node_metadata, dict):
            raise ValueError(f"{node_id}.metadata must be a dict when present.")
        node_metadata = dict(raw_node_metadata)
        node_metadata["is_final_answer_node"] = is_final_node
        if is_final_node:
            node_metadata["final_answer_contract"] = dict(final_answer_contract)
            node_metadata["value_format"] = final_answer_contract["format"]
            allowed_values = final_answer_contract.get("allowed_values", [])
            if allowed_values:
                node_metadata["allowed_values"] = list(allowed_values)

        instruction = raw_node.get("instruction")
        if instruction is not None and not isinstance(instruction, str):
            raise ValueError(f"{node_id}.instruction must be a string when present.")
        if instruction is None:
            instruction = NORMAL_EXECUTION_INSTRUCTION

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
    metadata["planner_schema_version"] = "task_topology_v2"
    metadata["final_answer_contract"] = final_answer_contract
    metadata["final_answer_node_id"] = final_answer_node_id
    metadata["dependency_map"] = dependency_map

    return PlanGraph(
        question_text=question_text,
        nodes=nodes,
        metadata=metadata,
    )


def _normalize_final_answer_contract(raw_contract: Any) -> dict[str, Any]:
    if not isinstance(raw_contract, dict):
        raise ValueError("decomposition is missing final_answer_contract, or it is not a dict.")

    fmt = raw_contract.get("format")
    if fmt not in VALID_FINAL_ANSWER_FORMATS:
        raise ValueError(f"Invalid final_answer_contract.format: {fmt!r}.")

    allowed_values = raw_contract.get("allowed_values", [])
    if allowed_values is None:
        allowed_values = []
    if not isinstance(allowed_values, list):
        raise ValueError("final_answer_contract.allowed_values must be a list.")

    normalized_allowed_values = [str(value).strip() for value in allowed_values if str(value).strip()]

    if fmt == "choice_label" and not normalized_allowed_values:
        raise ValueError("choice_label final_answer_contract must have non-empty allowed_values.")

    return {
        "format": fmt,
        "allowed_values": normalized_allowed_values,
    }


def _index_raw_subproblems(raw_subproblems: list[Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    for raw_node in raw_subproblems:
        if not isinstance(raw_node, dict):
            raise ValueError("Each subproblem/node must be a dict.")

        node_id = _required_str(raw_node, "id")
        if node_id in index:
            raise ValueError(f"Duplicate subproblem id: {node_id}.")
        index[node_id] = raw_node

    return index


def _derive_dependency_map(
    raw_subproblems: list[Any],
    subproblem_index: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    dependency_map: dict[str, list[str]] = {}

    for raw_node in raw_subproblems:
        if not isinstance(raw_node, dict):
            raise ValueError("Each subproblem/node must be a dict.")

        node_id = _required_str(raw_node, "id")
        deps: list[str] = []

        raw_inputs = raw_node.get(
            "inputs_from_subproblems",
            raw_node.get("inputs_from_nodes", raw_node.get("inputs", [])),
        )
        if raw_inputs is None:
            raw_inputs = []
        if not isinstance(raw_inputs, list):
            raise ValueError(f"{node_id}.inputs_from_subproblems must be a list.")

        for item in raw_inputs:
            if not isinstance(item, dict):
                raise ValueError(f"Each input selector in {node_id} must be a dict.")

            source_id = (
                item.get("source_subproblem_id")
                or item.get("source_node_id")
                or item.get("source")
            )
            field = item.get("field")

            if not isinstance(source_id, str) or not source_id.strip():
                raise ValueError(f"Malformed input selector in {node_id}: missing source id.")
            if not isinstance(field, str) or not field.strip():
                raise ValueError(f"Malformed input selector in {node_id}: missing field.")

            source_id = source_id.strip()
            field = field.strip()

            if source_id not in subproblem_index:
                raise ValueError(f"Subproblem {node_id} references unknown source {source_id}.")

            _find_raw_output_spec(subproblem_index[source_id], field)

            if source_id not in deps:
                deps.append(source_id)

        dependency_map[node_id] = deps

    return dependency_map


def _assert_valid_dag(dependency_map: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(node_id: str) -> None:
        if node_id in visiting:
            raise ValueError(f"Cycle detected in dependency graph at node {node_id}.")
        if node_id in visited:
            return

        visiting.add(node_id)
        for dep_id in dependency_map.get(node_id, []):
            dfs(dep_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in dependency_map:
        dfs(node_id)


def _find_unique_terminal_node_id(dependency_map: dict[str, list[str]]) -> str:
    node_ids = set(dependency_map.keys())
    used_as_dependency: set[str] = set()

    for deps in dependency_map.values():
        used_as_dependency.update(deps)

    terminal_nodes = sorted(node_id for node_id in node_ids if node_id not in used_as_dependency)

    if len(terminal_nodes) != 1:
        raise ValueError(f"Expected exactly one terminal subproblem, got {terminal_nodes}.")

    return terminal_nodes[0]


def _find_raw_output_spec(raw_node: dict[str, Any], field: str) -> dict[str, Any]:
    raw_outputs = raw_node.get("outputs", [])
    if not isinstance(raw_outputs, list):
        raise ValueError(f"{raw_node.get('id')}.outputs must be a list.")

    for output in raw_outputs:
        if isinstance(output, dict) and output.get("field") == field:
            return output

    raise ValueError(
        f"Field {field!r} not found in outputs of subproblem {raw_node.get('id')!r}."
    )


def _convert_inputs(raw_inputs: Any) -> list[ArtifactSelector]:
    if raw_inputs is None:
        return []

    if not isinstance(raw_inputs, list):
        raise ValueError("inputs_from_subproblems must be a list.")

    inputs: list[ArtifactSelector] = []

    for item in raw_inputs:
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

    for item in raw_outputs:
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
