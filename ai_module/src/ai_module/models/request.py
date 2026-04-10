"""Request validation models for the analysis endpoint.

This module defines the input schema for the /analyze endpoint,
ensuring strict validation of the analysis identifier.
"""

from __future__ import annotations

from pydantic import UUID4, BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    """Esquema de requisição para o endpoint POST /analyze.

    Parameters
    ----------
    analysis_id : UUID4
        Identificador único desta requisição de análise.
        Deve estar no formato UUID v4 válido.
    """

    model_config = ConfigDict(extra="forbid")

    analysis_id: UUID4 = Field(
        description="Unique identifier for the analysis request (UUID v4 format)"
    )