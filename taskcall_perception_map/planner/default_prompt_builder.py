"""Concrete prompt builder for LLM-based task decomposition."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from taskcall_perception_map.planner.models import PlannerRequest
from taskcall_perception_map.planner.instructions import ZERO_SHOT_DECOMPOSITION_INSTRUCTION


DEFAULT_PLANNER_INSTRUCTION = ZERO_SHOT_DECOMPOSITION_INSTRUCTION


class DefaultPlannerPromptBuilder:
    """Build a planning prompt from the normalized planner request."""

    def __init__(
        self,
        *,
        instruction: str = ZERO_SHOT_DECOMPOSITION_INSTRUCTION,
        include_metadata: bool = True,
        include_retrieved_cases: bool = True,
    ) -> None:
        self.instruction = instruction.strip()
        self.include_metadata = include_metadata
        self.include_retrieved_cases = include_retrieved_cases

    def build(self, request: PlannerRequest) -> str:
        instruction = self.instruction.strip()

        if instruction.endswith("Problem:"):
            instruction = instruction[: -len("Problem:")].rstrip()

        sections = [instruction]

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

        sections.append("Problem:\n" + request.question_text.strip())

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