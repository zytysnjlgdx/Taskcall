"""OpenAI-compatible provider implementation for the shared LLM layer."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib import error, request

from taskcall_perception_map.llm.config import LLMProviderConfig
from taskcall_perception_map.llm.errors import (
    LLMAuthenticationError,
    LLMRateLimitError,
    LLMResponseFormatError,
    LLMTransportError,
)
from taskcall_perception_map.llm.models import LLMRequest, LLMResponse, LLMUsage


class OpenAICompatibleClient:
    """Talk to any provider exposing the `/chat/completions` contract."""

    def __init__(self, *, config: LLMProviderConfig) -> None:
        self.config = config

    async def generate(self, request_data: LLMRequest) -> LLMResponse:
        payload = self._build_payload(request_data)
        raw_response = await asyncio.to_thread(self._post_json, payload)
        return self._parse_response(raw_response)

    def _build_payload(self, request_data: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request_data.model or self.config.default_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request_data.messages
            ],
            "temperature": request_data.temperature,
            "max_tokens": request_data.max_tokens,
        }
        if request_data.stop_sequences:
            payload["stop"] = list(request_data.stop_sequences)
        if request_data.response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        payload.update(request_data.provider_params)
        return payload

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            **self.config.extra_headers,
        }
        http_request = request.Request(
            url=url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(
                http_request,
                timeout=self.config.timeout_seconds,
            ) as response:
                raw_body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise self._map_http_error(exc.code, error_body) from exc
        except error.URLError as exc:
            raise LLMTransportError(str(exc.reason)) from exc

        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMResponseFormatError(
                "Provider returned a non-JSON response."
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMResponseFormatError(
                "Provider returned an unexpected JSON response shape."
            )
        return parsed

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseFormatError(
                "Provider response does not contain any choices."
            ) from exc

        message = choice.get("message", {})
        content = self._coerce_content(message.get("content"))
        usage_payload = data.get("usage") or {}
        usage = LLMUsage(
            input_tokens=usage_payload.get("prompt_tokens"),
            output_tokens=usage_payload.get("completion_tokens"),
        )
        return LLMResponse(
            content=content,
            raw=data,
            finish_reason=choice.get("finish_reason"),
            usage=usage,
        )

    @staticmethod
    def _coerce_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        text_chunks.append(text_value)
            if text_chunks:
                return "\n".join(text_chunks)
        raise LLMResponseFormatError(
            "Provider response does not contain a usable text message."
        )

    @staticmethod
    def _map_http_error(status_code: int, body: str) -> Exception:
        if status_code in {401, 403}:
            return LLMAuthenticationError(body or "Authentication failed.")
        if status_code == 429:
            return LLMRateLimitError(body or "Provider rate limit exceeded.")
        return LLMTransportError(
            f"Provider request failed with HTTP {status_code}: {body}"
        )
