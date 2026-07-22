from fastapi import status


def test_root_endpoint_success(client):
    """Test that hitting the API root path returns a redirect info page."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "online"
    assert "documentation" in response.json()


def test_healthcheck_endpoint_success(client):
    """Test that hitting the API health check endpoint returns 200 and indicates healthy database/service."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["status"] == "healthy"
    assert "environment" in data
    assert "timestamp" in data

    # Verify database section
    assert "database" in data
    assert data["database"]["status"] == "healthy"
    assert data["database"]["details"] is None
