"""Definitions and lookup rules for child worker-agent selection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentDefinition:
    """Declarative description of one child-agent archetype."""

    agent_type: str
    description: str
    supported_capabilities: list[str]
    preferred_keywords: list[str] = field(default_factory=list)
    default_instruction: str | None = None
    can_delegate: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentRegistry:
    """Resolve the best child-agent definition for a spawned subtask."""

    def __init__(self) -> None:
        self._definitions: dict[str, AgentDefinition] = {}

    def register(self, definition: AgentDefinition) -> None:
        self._definitions[definition.agent_type] = definition

    def get(self, agent_type: str) -> AgentDefinition | None:
        return self._definitions.get(agent_type)

    def list_all(self) -> list[AgentDefinition]:
        return list(self._definitions.values())

    def select(
        self,
        *,
        task_goal: str,
        requested_agent_type: str | None = None,
        required_capabilities: list[str] | None = None,
    ) -> AgentDefinition:
        required = required_capabilities or []

        if requested_agent_type:
            definition = self.get(requested_agent_type)
            if definition is None:
                raise KeyError(f"Unknown agent type: {requested_agent_type}")
            self._assert_capabilities(definition, required)
            return definition

        candidates = [
            definition
            for definition in self._definitions.values()
            if self._supports_all(definition, required)
        ]
        if not candidates:
            required_text = ", ".join(required) if required else "none"
            raise LookupError(
                "No agent definition matches the requested capabilities: "
                f"{required_text}"
            )

        goal_text = task_goal.lower()
        return max(
            candidates,
            key=lambda definition: (
                self._score_keywords(definition, goal_text),
                -len(definition.supported_capabilities),
                definition.agent_type,
            ),
        )

    @staticmethod
    def _supports_all(
        definition: AgentDefinition,
        required_capabilities: list[str],
    ) -> bool:
        supported = set(definition.supported_capabilities)
        return all(capability in supported for capability in required_capabilities)

    def _assert_capabilities(
        self,
        definition: AgentDefinition,
        required_capabilities: list[str],
    ) -> None:
        if self._supports_all(definition, required_capabilities):
            return
        missing = [
            capability
            for capability in required_capabilities
            if capability not in definition.supported_capabilities
        ]
        missing_text = ", ".join(missing)
        raise ValueError(
            f"Agent type {definition.agent_type} does not support: {missing_text}"
        )

    @staticmethod
    def _score_keywords(definition: AgentDefinition, goal_text: str) -> int:
        return sum(
            1
            for keyword in definition.preferred_keywords
            if keyword.lower() in goal_text
        )
