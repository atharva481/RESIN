from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "RESIN" in response.json()["message"]
