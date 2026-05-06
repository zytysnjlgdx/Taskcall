"""Parse structured planner JSON into domain plan objects."""

from __future__ import annotations

from typing import Any, cast

from taskcall_perception_map.domain.models import (
    ArtifactSelector,
    ArtifactType,
    OutputSpec,
    PlanGraph,
    PlanNode,
)
from taskcall_perception_map.llm.structured import parse_json_response


class JSONPlannerResponseParser:
    """Parse a JSON planner response into a concrete plan graph."""

    def parse(self, text: str) -> PlanGraph:
        payload = parse_json_response(text)
        graph_payload = _unwrap_plan_payload(payload)
        question_text = _read_str(
            graph_payload,
            "question_text",
            fallback=payload.get("question_text", ""),
        )
        metadata = _read_dict(graph_payload.get("metadata"))
        node_payloads = _read_list(graph_payload.get("nodes"), field_name="nodes")
        nodes = [self._parse_node(node_payload) for node_payload in node_payloads]
        return PlanGraph(
            question_text=question_text,
            nodes=nodes,
            metadata=metadata,
        )

    def _parse_node(self, raw_node: Any) -> PlanNode:
        if not isinstance(raw_node, dict):
            raise ValueError("Each planner node must be a JSON object.")

        node_id = _read_required_str(raw_node, "id")
        goal = _read_required_str(raw_node, "goal")
        evidence = _read_str_list(
            raw_node.get("evidence_from_question", raw_node.get("evidence", [])),
            field_name=f"{node_id}.evidence_from_question",
        )
        inputs_payload = raw_node.get(
            "inputs_from_subproblems",
            raw_node.get("inputs", []),
        )
        outputs_payload = raw_node.get("outputs", [])
        depends_on = _read_str_list(
            raw_node.get("depends_on", raw_node.get("dependencies", [])),
            field_name=f"{node_id}.depends_on",
        )
        agent_profile = _read_str(
            raw_node,
            "agent_profile",
            fallback=_read_str(raw_node, "agent_type", fallback="general_worker"),
        )
        tool_policy = _read_str_list(
            raw_node.get("tool_policy", raw_node.get("allowed_capabilities", [])),
            field_name=f"{node_id}.tool_policy",
        )
        instruction = raw_node.get("instruction")
        if instruction is not None and not isinstance(instruction, str):
            raise ValueError(f"{node_id}.instruction must be a string when present.")

        return PlanNode(
            id=node_id,
            goal=goal,
            evidence_from_question=evidence,
            inputs_from_subproblems=self._parse_inputs(inputs_payload, node_id=node_id),
            outputs=self._parse_outputs(outputs_payload, node_id=node_id),
            depends_on=depends_on,
            agent_profile=agent_profile,
            tool_policy=tool_policy,
            instruction=instruction,
            metadata=_read_dict(raw_node.get("metadata")),
        )

    @staticmethod
    def _parse_inputs(payload: Any, *, node_id: str) -> list[ArtifactSelector]:
        input_items = _read_list(payload, field_name=f"{node_id}.inputs_from_subproblems")
        selectors: list[ArtifactSelector] = []
        for index, item in enumerate(input_items):
            if not isinstance(item, dict):
                raise ValueError(
                    f"{node_id}.inputs_from_subproblems[{index}] must be an object."
                )
            source_node_id = _read_required_str(
                item,
                "source_node_id",
                fallback=item.get("source"),
            )
            field = _read_required_str(item, "field")
            required = item.get("required", True)
            if not isinstance(required, bool):
                raise ValueError(
                    f"{node_id}.inputs_from_subproblems[{index}].required must be a bool."
                )
            selectors.append(
                ArtifactSelector(
                    source_node_id=source_node_id,
                    field=field,
                    required=required,
                )
            )
        return selectors

    @staticmethod
    def _parse_outputs(payload: Any, *, node_id: str) -> list[OutputSpec]:
        output_items = _read_list(payload, field_name=f"{node_id}.outputs")
        outputs: list[OutputSpec] = []
        for index, item in enumerate(output_items):
            if not isinstance(item, dict):
                raise ValueError(f"{node_id}.outputs[{index}] must be an object.")
            field = _read_required_str(item, "field")
            description = _read_str(item, "description", fallback=field)
            artifact_type_value = _read_str(item, "artifact_type", fallback="value")
            required = item.get("required", True)
            if not isinstance(required, bool):
                raise ValueError(f"{node_id}.outputs[{index}].required must be a bool.")
            outputs.append(
                OutputSpec(
                    field=field,
                    artifact_type=cast(ArtifactType, artifact_type_value),
                    description=description,
                    required=required,
                )
            )
        return outputs


def _unwrap_plan_payload(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("plan_graph", payload.get("plan", payload.get("graph")))
    if nested is None:
        return payload
    if not isinstance(nested, dict):
        raise ValueError("Planner response plan payload must be a JSON object.")
    return nested


def _read_required_str(
    data: dict[str, Any],
    key: str,
    *,
    fallback: Any | None = None,
) -> str:
    value = data.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Planner response field '{key}' must be a non-empty string.")
    return value.strip()


def _read_str(data: dict[str, Any], key: str, *, fallback: Any) -> str:
    value = data.get(key, fallback)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"Planner response field '{key}' must be a string.")
    return value.strip()


def _read_list(value: Any, *, field_name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"Planner response field '{field_name}' must be a list.")
    return value


def _read_str_list(value: Any, *, field_name: str) -> list[str]:
    items = _read_list(value, field_name=field_name)
    text_items: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name}[{index}] must be a non-empty string.")
        text_items.append(item.strip())
    return text_items


def _read_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Planner metadata must be a JSON object when present.")
    return dict(value)
