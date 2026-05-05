"""LLM-backed planning agent skeleton.

This file intentionally stops at interface wiring. Prompt design,
response parsing, and retry/repair behavior can be implemented later
without changing the outer planner contract.
"""

from __future__ import annotations

from taskcall_perception_map.llm.base import LLMClient
from taskcall_perception_map.planner.models import PlannerRequest, PlannerResult
from taskcall_perception_map.planner.parser import PlannerResponseParser
from taskcall_perception_map.planner.prompt_builder import PlannerPromptBuilder
from taskcall_perception_map.planner.validator import PlanValidator


class LLMPlanningAgent:
    """Compose LLM, prompt builder, parser, and validator into one planner."""

    def __init__(
        self,
        *,
        llm_client: LLMClient,
        prompt_builder: PlannerPromptBuilder,
        response_parser: PlannerResponseParser,
        validator: PlanValidator,
        model: str,
        temperature: float = 0.1,
        max_tokens: int = 4_000,
    ) -> None:
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
        self.response_parser = response_parser
        self.validator = validator
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    async def plan(self, request: PlannerRequest) -> PlannerResult:
        """Plan generation is intentionally deferred to a later implementation."""
        raise NotImplementedError(
            "LLMPlanningAgent.plan() is not implemented yet. "
            "This class currently defines the stable planner interface only."
        )
