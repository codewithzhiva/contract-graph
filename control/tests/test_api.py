import os
from pathlib import Path

os.environ["DATABASE_PATH"] = str(Path(__file__).parent / "test.db")

from fastapi.testclient import TestClient

from app.main import app


def test_runtime_aware_comparison():
    with TestClient(app) as client:
        recorded = client.post(
            "/v1/runtime/observations",
            json={
                "observations": [
                    {
                        "consumer": "checkout",
                        "provider": "users",
                        "route": "/users/42",
                        "method": "GET",
                        "status_code": 200,
                        "latency_ms": 4,
                        "fields": ["id", "email"],
                    }
                ]
            },
        )
        assert recorded.status_code == 202
        old = {
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {"schema": {"properties": {"id": {}, "email": {}}}}
                                }
                            }
                        }
                    }
                }
            }
        }
        new = {
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"properties": {"id": {}}}}}}
                        }
                    }
                }
            }
        }
        baseline = client.post(
            "/v1/specs", json={"service": "users", "version": "1", "document": old}
        ).json()["id"]
        candidate = client.post(
            "/v1/specs", json={"service": "users", "version": "2", "document": new}
        ).json()["id"]
        report = client.post(
            "/v1/comparisons", json={"baseline_id": baseline, "candidate_id": candidate}
        ).json()
        assert report["risk"] == "high"
        assert report["affected_consumers"][0]["consumer"] == "checkout"


def test_unknown_spec_is_404():
    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/comparisons", json={"baseline_id": "missing", "candidate_id": "missing"}
            ).status_code
            == 404
        )
