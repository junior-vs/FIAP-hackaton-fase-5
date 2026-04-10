from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient

from ai_module.api.routes import set_service_health
from ai_module.core.metrics import metrics


def test_health_returns_503_when_service_is_degraded(client: TestClient) -> None:
    set_service_health(False)

    try:
        response = client.get("/health")
    finally:
        set_service_health(True)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    body = response.json()
    assert body["detail"]["status"] == "degraded"
    assert "llm_provider" in body["detail"]


def test_health_returns_200_when_service_is_healthy(client: TestClient) -> None:
    set_service_health(True)

    response = client.get("/health")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["status"] == "healthy"
    assert "llm_provider" in body


def test_metrics_endpoint_returns_expected_prometheus_lines(client: TestClient) -> None:
    original = (
        metrics.requests_success,
        metrics.requests_error,
        metrics.processing_time_ms_total,
        metrics.llm_retries_total,
    )
    metrics.requests_success = 7
    metrics.requests_error = 3
    metrics.processing_time_ms_total = 1234
    metrics.llm_retries_total = 2

    try:
        response = client.get("/metrics")
    finally:
        (
            metrics.requests_success,
            metrics.requests_error,
            metrics.processing_time_ms_total,
            metrics.llm_retries_total,
        ) = original

    assert response.status_code == status.HTTP_200_OK
    text = response.text
    assert "# HELP ai_module_requests_success_total" in text
    assert "ai_module_requests_success_total 7" in text
    assert "ai_module_requests_error_total 3" in text
    assert "ai_module_processing_time_ms_total 1234" in text
    assert "ai_module_llm_retries_total 2" in text
