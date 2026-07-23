from fastapi.testclient import TestClient

from app.main import app


def test_application_serves_health_check_and_dashboard() -> None:
    with TestClient(app) as client:
        health_response = client.get("/health")
        dashboard_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert dashboard_response.status_code == 200
    assert "AI Radar" in dashboard_response.text

