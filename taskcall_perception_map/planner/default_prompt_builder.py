"""Concrete prompt builder for LLM-based task decomposition."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from taskcall_perception_map.planner.models import PlannerRequest

DEFAULT_PLANNER_INSTRUCTION = """You are a planning agent that decomposes one user task into a DAG.

Return JSON only. Do not include markdown fences or explanatory prose.

The JSON object must contain:
- question_text: the original task text
- nodes: a list of plan nodes

Each node must contain:
- id: short unique string
- goal: the subtask the node solves
- evidence_from_question: list of short facts copied or derived from the user task
- inputs_from_subproblems: list of objects with source_node_id, field, and optional required
- outputs: list of objects with field, artifact_type, description, and optional required
- depends_on: list of upstream node ids
- agent_profile: short worker profile name
- tool_policy: list of allowed capability names

Keep the graph executable:
- dependencies must form a DAG
- nodes with no dependencies should be independently runnable
- downstream nodes should explicitly reference upstream artifacts
- outputs should be specific enough for another node to consume
"""


class DefaultPlannerPromptBuilder:
    """Build a planning prompt from the normalized planner request."""

    def __init__(
        self,
        *,
        instruction: str = DEFAULT_PLANNER_INSTRUCTION,
        include_metadata: bool = True,
        include_retrieved_cases: bool = True,
    ) -> None:
        self.instruction = instruction.strip()
        self.include_metadata = include_metadata
        self.include_retrieved_cases = include_retrieved_cases

    def build(self, request: PlannerRequest) -> str:
        sections = [self.instruction]

        if self.include_metadata:
            metadata_block = _compact_metadata(request.metadata)
            if metadata_block is not None:
                sections.append("Planner metadata:\n" + metadata_block)

        if self.include_retrieved_cases and request.retrieved_cases:
            cases_payload = [self._serialize_case(case) for case in request.retrieved_cases]
            sections.append(
                "Retrieved reference cases:\n"
                + json.dumps(cases_payload, ensure_ascii=True, indent=2)
            )

        sections.append("Task to decompose:\n" + request.question_text.strip())
        sections.append(
            "Output schema reminder:\n"
            '{\n'
            '  "question_text": "...",\n'
            '  "nodes": [\n'
            "    {\n"
            '      "id": "node_id",\n'
            '      "goal": "...",\n'
            '      "evidence_from_question": ["..."],\n'
            '      "inputs_from_subproblems": [\n'
            '        {"source_node_id": "upstream_node", "field": "field_name"}\n'
            "      ],\n"
            '      "outputs": [\n'
            '        {"field": "field_name", "artifact_type": "value", "description": "..."}\n'
            "      ],\n"
            '      "depends_on": ["upstream_node"],\n'
            '      "agent_profile": "general_worker",\n'
            '      "tool_policy": []\n'
            "    }\n"
            "  ]\n"
            "}"
        )
        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _serialize_case(case: Any) -> dict[str, Any]:
        case_dict = asdict(case)
        case_dict.pop("score", None)
        return case_dict


def _compact_metadata(metadata: dict[str, Any]) -> str | None:
    visible_metadata = {
        key: value for key, value in metadata.items() if key != "provider_params"
    }
    if not visible_metadata:
        return None
    return json.dumps(visible_metadata, ensure_ascii=True, indent=2, default=str)
