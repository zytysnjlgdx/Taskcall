"""Common error types raised by the LLM abstraction layer."""

from __future__ import annotations


class LLMError(RuntimeError):
    """Base class for model-call failures."""


class LLMTransportError(LLMError):
    """Network or transport-level failure."""


class LLMAuthenticationError(LLMError):
    """Authentication or authorization failure."""


class LLMRateLimitError(LLMError):
    """Provider rejected the request due to rate limiting."""


class LLMResponseFormatError(LLMError):
    """Provider returned a response that cannot be parsed as expected."""
