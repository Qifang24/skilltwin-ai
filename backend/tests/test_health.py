"""健康检查与应用装配的冒烟测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_root_returns_service_info(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "SkillTwin AI"
    assert body["health"] == "/api/v1/health"


def test_health_reports_all_components(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()

    assert body["status"] in {"ok", "degraded"}
    assert body["app"] == "SkillTwin AI"

    names = {c["name"] for c in body["components"]}
    assert names == {"database", "llm", "embedding", "vector_store"}


def test_health_database_is_reachable(client: TestClient) -> None:
    components = {c["name"]: c for c in client.get("/api/v1/health").json()["components"]}
    assert components["database"]["ok"] is True, components["database"]["detail"]


def test_health_llm_ok_under_echo_provider(client: TestClient) -> None:
    """conftest 把 provider 设为 echo，不应因缺 API Key 而报错。"""
    components = {c["name"]: c for c in client.get("/api/v1/health").json()["components"]}
    assert components["llm"]["ok"] is True


def test_openapi_schema_is_generated(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/health" in resp.json()["paths"]


def test_unknown_route_returns_404(client: TestClient) -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
