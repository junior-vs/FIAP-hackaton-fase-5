"""Pydantic models for architecture analysis reports.

The models in this module follow the report contract defined in `specs/spec.md`.
All models reject unknown fields (`extra="forbid"`) and enforce strict enums.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComponentType(str, Enum):
    """Categorias de componentes de arquitetura suportados."""

    SERVICE = "service"
    DATABASE = "database"
    QUEUE = "queue"
    GATEWAY = "gateway"
    CACHE = "cache"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    """Níveis de severidade de risco."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    """Níveis de prioridade de recomendação."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Component(BaseModel):
    """Componente identificado no diagrama de arquitetura."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    type: ComponentType
    description: str = Field(min_length=1, max_length=500)


class Risk(BaseModel):
    """Risco identificado durante a análise de arquitetura."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    severity: Severity
    description: str = Field(min_length=1, max_length=500)
    affected_components: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    """Ação recomendada para melhorar a arquitetura."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    priority: Priority
    description: str = Field(min_length=1, max_length=500)


class Report(BaseModel):
    """Payload principal do relatório retornado pelo pipeline de IA."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=500)
    components: list[Component] = Field(min_length=1)
    risks: list[Risk] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class ReportMetadata(BaseModel):
    """Metadados descrevendo como o relatório foi gerado."""

    model_config = ConfigDict(extra="forbid")

    model_used: str = Field(min_length=1)
    processing_time_ms: int = Field(ge=0)
    input_type: Literal["image", "pdf"]


class AnalyzeResponse(BaseModel):
    """Contrato de resposta de sucesso para POST /analyze."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(min_length=1)
    status: Literal["success"] = "success"
    report: Report
    metadata: ReportMetadata


class ErrorResponse(BaseModel):
    """Contrato de resposta de erro para POST /analyze."""

    model_config = ConfigDict(extra="forbid")

    analysis_id: str = Field(min_length=1)
    status: Literal["error"] = "error"
    error_code: str = Field(min_length=1)
    message: str = Field(min_length=1)