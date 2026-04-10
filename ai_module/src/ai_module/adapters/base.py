"""Base interface for LLM adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMAdapter(ABC):
    """Classe base abstrata para todos os adaptadores de provedores LLM."""

    @abstractmethod
    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Send an image and prompt to the LLM provider and return the raw response.

        Raises:
            LLMTimeoutError: if the call exceeds the configured timeout.
            LLMCallError: on SDK or provider failure.
        """
        ...
