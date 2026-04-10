"""Adapter for the Google Gemini generative AI API."""

from __future__ import annotations

import asyncio

from google import genai
from google.genai import types

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import LLMCallError, LLMTimeoutError
from ai_module.core.settings import settings


class GeminiAdapter(LLMAdapter):
    """Implementação Gemini do contrato de adaptador LLM."""

    def __init__(
        self,
        api_key: str = settings.GEMINI_API_KEY,
        model: str = settings.LLM_MODEL,
    ) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model_name = model

    async def analyze(self, image_bytes: bytes, prompt: str, system_prompt: str) -> str:
        """Chama o Gemini com a imagem renderizada e o texto de prompt."""
        try:
            image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            config = types.GenerateContentConfig(system_instruction=system_prompt)

            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model_name,
                    contents=[prompt, image_part],
                    config=config,
                ),
                timeout=settings.LLM_TIMEOUT_SECONDS,
            )
            content = response.text
            if not content:
                raise LLMCallError("Gemini retornou uma resposta vazia.")
            return content

        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(
                f"Timeout após {settings.LLM_TIMEOUT_SECONDS}s chamando o Gemini."
            ) from e
        except (LLMTimeoutError, LLMCallError):
            raise
        except Exception as e:
            raise LLMCallError(f"Erro ao chamar o Gemini: {e}") from e