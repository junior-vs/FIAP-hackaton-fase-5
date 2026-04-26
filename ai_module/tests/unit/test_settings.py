"""Testes unitários para validações de configurações."""

from __future__ import annotations

import warnings

from ai_module.core.settings import Settings


def test_validate_api_keys_emite_alerta_quando_nenhuma_chave_existe() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        Settings(GEMINI_API_KEY="", OPENAI_API_KEY="", LLM_PROVIDER="gemini")

    assert captured is not None
    assert len(captured) == 1
    assert "Nenhuma chave de API" in str(captured[0].message)


def test_validate_api_keys_aceita_quando_ha_ao_menos_uma_chave() -> None:
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        settings = Settings(GEMINI_API_KEY="", OPENAI_API_KEY="openai-key", LLM_PROVIDER="gemini")

    assert captured is not None
    assert settings.OPENAI_API_KEY == "openai-key"
    assert captured == []
