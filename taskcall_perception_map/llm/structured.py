"""Helpers for parsing and validating structured LLM responses."""

from __future__ import annotations

import json
from typing import Any

from taskcall_perception_map.llm.errors import LLMResponseFormatError


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON text, tolerating fenced markdown code blocks.从 LLM 的原始回复中提取出纯 JSON dict"""
    normalized = text.strip()
    if normalized.startswith("```"):
        normalized = _strip_code_fence(normalized)

    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise LLMResponseFormatError("LLM response is not valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise LLMResponseFormatError("Expected a top-level JSON object.")
    return parsed


def require_fields(data: dict[str, Any], required_fields: list[str]) -> None:
    """Raise when the parsed JSON response misses required fields."""
    missing = [field for field in required_fields if field not in data]
    if missing:
        missing_text = ", ".join(missing)
        raise LLMResponseFormatError(
            f"Structured response is missing required fields: {missing_text}"
        )


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
