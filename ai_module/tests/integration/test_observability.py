"""Integration tests for health and metrics observability endpoints."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.metrics import metrics
from ai_module.core.state import set_service_health
from ai_module.main import app


def test_health_healthy_response_schema(client: TestClient) -> None:
    set_service_health(True)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "healthy"
    assert "llm_provider" in body
    assert isinstance(body["llm_provider"], str)
    assert len(body["llm_provider"]) > 0


def test_health_degraded_response_schema(client: TestClient) -> None:
    set_service_health(False)

    try:
        response = client.get("/health")
    finally:
        set_service_health(True)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    detail = response.json()["detail"]
    assert detail["status"] == "degraded"
    assert "llm_provider" in detail
    assert isinstance(detail["llm_provider"], str)


def test_health_recovers_after_degraded(client: TestClient) -> None:
    set_service_health(False)
    degraded_response = client.get("/health")
    assert degraded_response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    set_service_health(True)
    healthy_response = client.get("/health")
    assert healthy_response.status_code == status.HTTP_200_OK


def test_metrics_response_content_type_is_plain_text(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    assert "text/plain" in response.headers["content-type"]


def test_metrics_contains_all_required_prometheus_keys(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "ai_requests_total" in text
    assert "ai_processing_time_ms_avg" in text
    assert "ai_llm_retries_total" in text
    assert "ai_llm_provider_active" in text


def test_metrics_contains_help_and_type_annotations(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "# HELP" in text
    assert "# TYPE" in text


def test_metrics_reflect_successful_analyze_request(
    client: TestClient,
    png_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    before = metrics.requests_success

    client.post(
        "/analyze",
        data={"analysis_id": "obs-test-01"},
        files={"file": ("diag.png", png_bytes, "image/png")},
    )

    assert metrics.requests_success == before + 1


def test_metrics_reflect_failed_analyze_request(
    client: TestClient,
    corrupted_bytes: bytes,
    mock_adapter: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(app.dependency_overrides, get_llm_adapter, lambda: mock_adapter)

    before = metrics.requests_error

    client.post(
        "/analyze",
        data={"analysis_id": "obs-test-02"},
        files={"file": ("bad.png", corrupted_bytes, "image/png")},
    )

    assert metrics.requests_error == before + 1
