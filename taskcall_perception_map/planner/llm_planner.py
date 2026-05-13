"""LLM-backed planning agent skeleton.

This file intentionally stops at interface wiring. Prompt design,
response parsing, and retry/repair behavior can be implemented later
without changing the outer planner contract.
"""

from __future__ import annotations

from taskcall_perception_map.llm import LLMMessage, LLMRequest
from taskcall_perception_map.llm.base import LLMClient
from taskcall_perception_map.planner.models import (
    PlannerDebugInfo,
    PlannerRequest,
    PlannerResult,
)
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
        """Build one plan graph from a normalized planner request."""
        prompt_text = self.prompt_builder.build(request)
        debug = PlannerDebugInfo(prompt_text=prompt_text)

        provider_params = request.metadata.get("provider_params", {})
        if not isinstance(provider_params, dict):
            provider_params = {}

        response = await self.llm_client.generate(
            LLMRequest(
                messages=[LLMMessage(role="user", content=prompt_text)],
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                response_format="json",
                provider_params=provider_params,
                metadata=dict(request.metadata),
            )
        )
        debug.raw_response = response.content
        if response.finish_reason:
            debug.notes.append(f"finish_reason={response.finish_reason}")

        plan = self.response_parser.parse(response.content)  # 将 LLM 返回的 JSON 字符串解析为 PlanGraph 对象
        if not plan.question_text:
            plan.question_text = request.question_text
        plan.metadata.setdefault("planner_model", self.model)

        validation = self.validator.validate(plan)  # 校验 PlanGraph 的结构合法性（节点引用、环检测等）
        if not validation.ok:
            issue_text = "; ".join(
                _format_validation_issue(issue) for issue in validation.issues
            )
            debug.notes.append(f"validation_failed={issue_text}")
            raise ValueError(f"Planner produced an invalid plan: {issue_text}")

        if response.usage is not None:
            debug.notes.append(
                "usage="
                f"input:{response.usage.input_tokens},"
                f"output:{response.usage.output_tokens}"
            )
        return PlannerResult(plan=plan, debug=debug)


def _format_validation_issue(issue: object) -> str:
    message = getattr(issue, "message", str(issue))
    node_id = getattr(issue, "node_id", None)
    if isinstance(node_id, str) and node_id:
        return f"{node_id}: {message}"
    return str(message)
