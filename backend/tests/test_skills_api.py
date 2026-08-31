"""技能表接口测试，含全局一致性守卫。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import SkillCategory, SkillStatus
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.models.ontology import Job, Skill
from app.schemas.skill import CATEGORY_PREFIX

SEED_FILE = (
    Path(__file__).resolve().parents[2] / "data" / "seed" / "skills_ai_data_annotator.json"
)


@pytest.fixture
def seeded(db: Session) -> Session:
    doc = KnowledgeDoc(
        id="doc_std",
        title="测试标准",
        source_name="《测试标准》",
        source_type="national_standard",
        standard_id="TEST-001",
    )
    chunk = KnowledgeChunk(
        id="doc_std#3", doc_id="doc_std", chunk_index=3, text="原文", page="6"
    )
    db.add_all(
        [
            doc,
            chunk,
            Skill(
                skill_code="data.cleaning",
                name_zh="数据清洗",
                category=SkillCategory.DATA,
                aliases=["数据预处理"],
                evidence=[
                    {
                        "chunk_id": "doc_std#3",
                        "page": "6",
                        "section": "3.1 五级/初级工",
                        "quote": "能根据标注规范和要求, 完成文本、视觉、语音数据清洗",
                    }
                ],
            ),
            Skill(
                skill_code="annot.image",
                name_zh="视觉数据标注",
                category=SkillCategory.ANNOTATION,
                aliases=["图像标注"],
            ),
        ]
    )
    db.commit()
    return db


def test_list_skills(client: TestClient, seeded: Session) -> None:
    body = client.get("/api/v1/skills").json()
    assert body["total"] == 2
    assert {i["skill_code"] for i in body["items"]} == {"data.cleaning", "annot.image"}


def test_list_skills_filtered_by_category(client: TestClient, seeded: Session) -> None:
    body = client.get("/api/v1/skills", params={"category": "annotation"}).json()
    assert body["total"] == 1
    assert body["items"][0]["skill_code"] == "annot.image"


def test_skill_detail_exposes_verifiable_source(
    client: TestClient, seeded: Session
) -> None:
    """「这个技能点凭什么存在」必须能下钻到标准原文的页码。"""
    body = client.get("/api/v1/skills/data.cleaning").json()

    assert body["name_zh"] == "数据清洗"
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["source_name"] == "《测试标准》"
    assert source["standard_id"] == "TEST-001"
    assert source["page"] == "6"
    assert "数据清洗" in source["quote"]


def test_missing_skill_returns_404(client: TestClient, seeded: Session) -> None:
    resp = client.get("/api/v1/skills/nope.nothing")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_normalize_endpoint(client: TestClient, seeded: Session) -> None:
    resp = client.post(
        "/api/v1/skills/normalize",
        json={"terms": ["数据清洗", "data.cleaning", "图像标注", "量子计算"]},
    )
    body = resp.json()

    assert body["matched_count"] == 3
    assert body["unmatched_count"] == 1
    codes = [m["skill_code"] for m in body["matches"]]
    assert codes == ["data.cleaning", "data.cleaning", "annot.image", None]


# ------------------------------------------------------------ 一致性守卫
def test_all_skill_references_resolve(db: Session) -> None:
    """风险 #2 的实际防线。

    数据库外键只保证「指向的技能存在」，管不住「指向了已废弃的技能」。
    后续 Phase 新增 course_skill / training_task_skill /
    assessment_item_skill / skill_profile_entry 时，此测试同步扩展。
    """
    db.add_all(
        [
            Job(id="ai_data_annotator", name="AI数据标注工程师"),
            Skill(
                skill_code="data.cleaning",
                name_zh="数据清洗",
                category=SkillCategory.DATA,
            ),
            Skill(
                skill_code="annot.old",
                name_zh="旧技能",
                category=SkillCategory.ANNOTATION,
                status=SkillStatus.DEPRECATED,
            ),
        ]
    )
    db.add(CompetencyGraph(id="g1", job_id="ai_data_annotator", version=1))
    db.add(
        CompetencyNode(
            id="g1.s1",
            graph_id="g1",
            node_type="skill_point",
            name="数据清洗",
            skill_code="data.cleaning",
        )
    )
    db.commit()

    active = {
        code
        for (code,) in db.execute(
            select(Skill.skill_code).where(Skill.status == SkillStatus.ACTIVE)
        )
    }
    referenced = {
        code
        for (code,) in db.execute(
            select(CompetencyNode.skill_code).where(
                CompetencyNode.skill_code.is_not(None)
            )
        )
    }
    dangling = referenced - active
    assert not dangling, f"这些技能引用无法解析到 active 技能：{sorted(dangling)}"


# ------------------------------------------------------------ 种子文件质量
@pytest.mark.skipif(not SEED_FILE.exists(), reason="种子文件尚未生成")
def test_seed_file_is_internally_consistent() -> None:
    """种子文件是技能表的源头，它自身出错会污染全系统。"""
    payload = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    skills = payload["skills"]

    codes = [s["skill_code"] for s in skills]
    assert len(codes) == len(set(codes)), "存在重复 skill_code"

    for skill in skills:
        code, category = skill["skill_code"], SkillCategory(skill["category"])
        assert code.split(".", 1)[0] == CATEGORY_PREFIX[category], (
            f"{code} 的前缀与 category={category.value} 不符"
        )
        assert skill["sources"], f"{code} 缺少来源引用"
        for source in skill["sources"]:
            assert source.get("quote"), f"{code} 的来源缺少引文"
            assert source.get("chunk_id"), f"{code} 的来源缺少 chunk_id"
        # 未经真实教师审核前不得标为 human_reviewed
        assert skill["provenance"] == "llm_drafted"
