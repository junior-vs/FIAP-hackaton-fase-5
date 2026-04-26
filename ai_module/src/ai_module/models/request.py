"""Request validation models for the analysis endpoint.

This module defines the input schema for the /analyze endpoint,
ensuring strict validation of the analysis identifier.
"""

from __future__ import annotations

import uuid

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator


class AnalyzeRequest(BaseModel):
    """Esquema de requisição para o endpoint POST /analyze.

    Parameters
    ----------
    analysis_id : UUID4
        Identificador único desta requisição de análise.
        Deve estar no formato UUID v4 válido.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(..., description="UUID da análise")
    context_text: str | None = Field(default=None, max_length=1000)

    @field_validator("analysis_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        """Valida se o analysis_id é um UUID4 válido."""
        try:
            uuid_obj = uuid.UUID(v, version=4)
            return str(uuid_obj)
        except ValueError:
            raise ValueError("analysis_id must be a valid UUID4 string")
        return v
    
    
