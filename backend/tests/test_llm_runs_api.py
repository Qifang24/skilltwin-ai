"""可解释性下钻接口测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import EvidenceType, LLMRunStatus
from app.models.audit import Citation, LLMRun


def _make_run(db: Session, run_id: str, agent: str = "competency_graph") -> LLMRun:
    run = LLMRun(
        id=run_id,
        agent=agent,
        provider="openai_compat",
        model="deepseek/deepseek-chat",
        prompt_hash=f"hash_{run_id}",
        input_summary={"job_id": "ai_data_annotator"},
        output_json={"nodes": [{"name": "数据标注能力"}]},
        raw_output='{"nodes": [{"name": "数据标注能力"}]}',
        tokens_in=120,
        tokens_out=340,
        latency_ms=2870,
        status=LLMRunStatus.SUCCESS,
    )
    db.add(run)
    db.commit()
    return run


def test_get_run_detail_exposes_full_provenance(client: TestClient, db: Session) -> None:
    run = _make_run(db, "run_detail_1")
    db.add(
        Citation(
            llm_run_id=run.id,
            claim="目标检测标注需保证矩形框紧贴目标边缘",
            marker="S1",
            evidence_type=EvidenceType.DOCUMENTARY,
            chunk_id=None,
            quote="矩形框应紧贴目标物体外接边缘",
            verified=True,
        )
    )
    db.commit()

    resp = client.get("/api/v1/llm-runs/run_detail_1")
    assert resp.status_code == 200
    body = resp.json()

    assert body["agent"] == "competency_graph"
    assert body["model"] == "deepseek/deepseek-chat"
    assert body["latency_ms"] == 2870
    assert body["raw_output"].startswith('{"nodes"')
    assert body["input_summary"]["job_id"] == "ai_data_annotator"
    assert len(body["citations"]) == 1
    assert body["citations"][0]["marker"] == "S1"
    assert body["citations"][0]["verified"] is True


def test_get_missing_run_returns_structured_404(client: TestClient) -> None:
    resp = client.get("/api/v1/llm-runs/run_does_not_exist")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_list_runs_is_paginated(client: TestClient, db: Session) -> None:
    for index in range(5):
        _make_run(db, f"run_list_{index}")

    resp = client.get("/api/v1/llm-runs", params={"limit": 2})
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    # 列表视图不应带上原始输出，避免响应体膨胀
    assert "raw_output" not in body["items"][0]


def test_list_runs_filters_by_agent(client: TestClient, db: Session) -> None:
    _make_run(db, "run_a", agent="competency_graph")
    _make_run(db, "run_b", agent="training_task")

    resp = client.get("/api/v1/llm-runs", params={"agent": "training_task"})
    body = resp.json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == "run_b"


def test_list_runs_filters_by_status(client: TestClient, db: Session) -> None:
    _make_run(db, "run_ok")
    failed = _make_run(db, "run_bad")
    failed.status = LLMRunStatus.PARSE_FAILED
    db.commit()

    resp = client.get("/api/v1/llm-runs", params={"status": "parse_failed"})
    body = resp.json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == "run_bad"
