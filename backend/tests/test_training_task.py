"""实训任务生成与发布测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.core.enums import (
    GraphStatus,
    NodeType,
    SkillCategory,
    TaskDifficulty,
    TaskStatus,
)
from app.core.errors import ConflictError, ValidationError
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan
from app.models.ontology import Job, Skill
from app.schemas.common import SourceRef
from app.schemas.training import (
    CommonMistake,
    RubricDimension,
    RubricLevel,
    TaskObjective,
    TaskStep,
    TrainingTaskDraft,
    GenerateTaskRequest,
)
from app.services.training_task_service import TrainingTaskService

SOURCES = [
    SourceRef(
        type="documentary",
        marker="S1",
        chunk_id="doc_std#10",
        source_name="《人工智能训练师国家职业技能标准（2021年版）》",
        page="6",
        quote="能根据标注规范和要求, 完成文本、视觉、语音数据标注",
    )
]


@pytest.fixture
def approved_graph(db: Session) -> Session:
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add_all(
        [
            Skill(skill_code="annot.image", name_zh="视觉数据标注", category=SkillCategory.ANNOTATION, aliases=["图像标注"]),
            Skill(skill_code="quality.audit", name_zh="标注数据审核", category=SkillCategory.QUALITY),
        ]
    )
    db.add(
        CompetencyGraph(
            id="g1", job_id="ai_data_annotator", version=1, status=GraphStatus.APPROVED
        )
    )
    db.add(CompetencyNode(id="g1.job", graph_id="g1", node_type=NodeType.JOB, name="AI数据标注工程师"))
    db.add(CompetencyNode(id="g1.cap1", graph_id="g1", parent_id="g1.job", node_type=NodeType.COMPETENCY, name="数据标注能力"))
    db.add(CompetencyNode(id="g1.unit1", graph_id="g1", parent_id="g1.cap1", node_type=NodeType.COMPETENCY_UNIT, name="原始数据清洗与标注"))
    db.add(CompetencyNode(id="g1.sp1", graph_id="g1", parent_id="g1.unit1", node_type=NodeType.SKILL_POINT, name="视觉数据标注", skill_code="annot.image", mastery_level=3))
    db.commit()
    return db


def _draft(**over) -> TrainingTaskDraft:
    return TrainingTaskDraft(
        title=over.get("title", "道路场景目标检测数据标注"),
        scenario="你是某自动驾驶公司的数据标注工程师，本周需要完成 500 张道路场景图片的目标检测标注。",
        difficulty=over.get("difficulty", TaskDifficulty.BEGINNER),
        est_minutes=90,
        objectives=over.get(
            "objectives",
            [TaskObjective(text="掌握矩形框标注规范", skill_code="annot.image")],
        )
        + [TaskObjective(text="理解标注质量控制流程")],
        steps=[
            TaskStep(order=1, title="熟悉标注规范", detail="阅读标注规范文档并理解各类目标的定义与边界要求。"),
            TaskStep(order=2, title="完成标注", detail="对分配的图片逐张完成矩形框标注，确保边界紧贴目标。"),
            TaskStep(order=3, title="自检提交", detail="按质量清单自检后提交标注结果与自检报告。"),
        ],
        deliverables=["标注结果文件（JSON）", "质量自检报告"],
        rubric=over.get(
            "rubric",
            [
                RubricDimension(
                    dimension="标注准确率",
                    weight=60,
                    levels=[
                        RubricLevel(level="优秀", criteria="准确率≥95%，边界紧贴目标"),
                        RubricLevel(level="合格", criteria="准确率≥85%"),
                    ],
                ),
                RubricDimension(
                    dimension="规范符合度",
                    weight=40,
                    levels=[
                        RubricLevel(level="优秀", criteria="完全符合标注规范"),
                        RubricLevel(level="合格", criteria="偶有偏差但不影响使用"),
                    ],
                ),
            ],
        ),
        common_mistakes=[
            CommonMistake(mistake="框选范围过大", consequence="模型学到无关背景特征", fix="边界紧贴目标外接矩形")
        ],
    )


def _persist(db: Session, draft: TrainingTaskDraft, node_id: str = "g1.unit1"):
    service = TrainingTaskService(db)
    node, _, _ = service.node_context(node_id)
    result = service.persist(node=node, draft=draft, sources=SOURCES)
    db.commit()
    return service, result


def _curriculum(db: Session) -> tuple[CurriculumPlan, CurriculumCourse]:
    plan = CurriculumPlan(
        id="plan_ai_2026",
        name="人工智能技术应用 2026",
        profession="人工智能技术应用",
        version="2026",
        source_name="校内人才培养方案",
        is_partial=False,
    )
    course = CurriculumCourse(
        id="course_annotation",
        plan_id=plan.id,
        course_code="AI204",
        name="智能数据标注实训",
        category="专业核心课",
        total_hours=48,
        objectives="掌握视觉数据标注规范与质量检查方法。",
        practical_content="完成道路场景目标检测数据标注。",
        learning_outcomes="提交标注结果和质量报告。",
        source_chunk_id="curriculum:course:1",
        source_page="12",
        source_quote="智能数据标注实训：完成道路场景目标检测数据标注，提交标注结果和质量报告。",
        field_evidence={
            "practical_content": {
                "chunk_id": "curriculum:course:1",
                "page": "12",
                "quote": "完成道路场景目标检测数据标注。",
            }
        },
    )
    db.add(plan)
    db.flush()
    db.add(course)
    db.flush()
    db.add(
        CourseSkillCoverage(
            course_id=course.id,
            skill_code="annot.image",
            coverage_strength=2,
            coverage_status="covered",
            source_chunk_id="curriculum:course:1",
            source_page="12",
            evidence_quote="掌握视觉数据标注规范。",
            teacher_confirmed=True,
        )
    )
    db.commit()
    return plan, course


# ---------------------------------------------------------------- 前置校验
def test_cannot_generate_from_draft_graph(db: Session) -> None:
    """草案图谱的节点编码还会变，据此生成任务会留下悬空引用。"""
    db.add(Job(id="ai_data_annotator", name="AI数据标注工程师"))
    db.add(CompetencyGraph(id="gd", job_id="ai_data_annotator", version=1))
    db.add(CompetencyNode(id="gd.unit1", graph_id="gd", node_type=NodeType.COMPETENCY_UNIT, name="单元"))
    db.commit()

    with pytest.raises(ValidationError, match="只能从已审核通过的图谱派生"):
        TrainingTaskService(db).node_context("gd.unit1")


def test_node_context_returns_path_and_skills(approved_graph: Session) -> None:
    node, path, skills = TrainingTaskService(approved_graph).node_context("g1.unit1")

    assert node.name == "原始数据清洗与标注"
    assert path == ["AI数据标注工程师", "数据标注能力", "原始数据清洗与标注"]
    assert skills == [("annot.image", "视觉数据标注", 3)]


# ---------------------------------------------------------------- 持久化
def test_task_is_structured_not_markdown(approved_graph: Session) -> None:
    """结构化是刻意的：rubric 后续要被测评环节直接读取。"""
    _, result = _persist(approved_graph, _draft())
    task = result.task

    assert task.status is TaskStatus.DRAFT
    assert len(task.steps) == 3
    assert task.steps[0]["order"] == 1
    assert task.rubric[0]["dimension"] == "标注准确率"
    assert task.rubric[0]["levels"][0]["level"] == "优秀"
    assert task.deliverables == ["标注结果文件（JSON）", "质量自检报告"]


def test_task_links_to_source_node_and_skills(approved_graph: Session) -> None:
    _, result = _persist(approved_graph, _draft())

    assert result.task.source_node_id == "g1.unit1"
    codes = {s.skill_code for s in result.task.skills}
    assert "annot.image" in codes


def test_legacy_generation_request_and_task_remain_unlinked(approved_graph: Session) -> None:
    """新增课程参数必须保持可选，旧教师端请求不需要改动即可继续使用。"""
    request = GenerateTaskRequest(node_id="g1.unit1")
    assert request.plan_id is None
    assert request.course_id is None

    _, result = _persist(approved_graph, _draft())
    assert result.task.plan_id is None
    assert result.task.course_id is None


def test_course_selection_is_inferred_validated_and_persisted(approved_graph: Session) -> None:
    plan, course = _curriculum(approved_graph)
    service = TrainingTaskService(approved_graph)
    node, _, _ = service.node_context("g1.unit1")

    curriculum = service.curriculum_context(node, course_id=course.id)
    assert curriculum is not None
    assert curriculum.plan.id == plan.id
    assert curriculum.course is course
    assert [item.skill_code for item in curriculum.mappings] == ["annot.image"]
    assert "课程已核验的技能覆盖" in curriculum.prompt_text()
    assert "完成道路场景目标检测数据标注" in curriculum.prompt_text()

    result = service.persist(
        node=node,
        draft=_draft(),
        sources=SOURCES,
        curriculum=curriculum,
    )
    approved_graph.commit()
    assert result.task.plan_id == plan.id
    assert result.task.course_id == course.id


def test_course_must_belong_to_selected_plan(approved_graph: Session) -> None:
    _, course = _curriculum(approved_graph)
    approved_graph.add(
        CurriculumPlan(
            id="another_plan",
            name="另一培养方案",
            source_name="校内材料",
        )
    )
    approved_graph.commit()
    node, _, _ = TrainingTaskService(approved_graph).node_context("g1.unit1")

    with pytest.raises(ValidationError, match="不属于所选培养方案"):
        TrainingTaskService(approved_graph).curriculum_context(
            node, plan_id="another_plan", course_id=course.id
        )


def test_task_detail_returns_curriculum_course_and_original_evidence(
    approved_graph: Session, client
) -> None:
    plan, course = _curriculum(approved_graph)
    service = TrainingTaskService(approved_graph)
    node, _, _ = service.node_context("g1.unit1")
    curriculum = service.curriculum_context(node, course_id=course.id)
    result = service.persist(
        node=node,
        draft=_draft(),
        sources=SOURCES,
        curriculum=curriculum,
    )
    approved_graph.commit()

    response = client.get(f"/api/v1/training-tasks/{result.task.id}")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["plan_id"] == plan.id
    assert payload["course_id"] == course.id
    assert payload["curriculum_plan"]["name"] == plan.name
    assert payload["curriculum_course"]["name"] == course.name
    evidence_types = {item["evidence_type"] for item in payload["course_evidence"]}
    assert {"course_source", "course_field", "skill_coverage"} <= evidence_types
    assert any("道路场景目标检测" in item["quote"] for item in payload["course_evidence"])
    assert all(item["is_generation_snapshot"] for item in payload["course_evidence"])

    # 任务解释的是生成时依据；后来改课程或映射不能悄悄改写历史。
    course.source_quote = "后来修改且不应覆盖任务历史的课程文字"
    mapping = approved_graph.query(CourseSkillCoverage).filter_by(
        course_id=course.id, skill_code="annot.image"
    ).one()
    mapping.evidence_quote = "后来修改的映射文字"
    approved_graph.commit()
    refreshed = client.get(f"/api/v1/training-tasks/{result.task.id}").json()
    quotes = [item["quote"] for item in refreshed["course_evidence"]]
    assert any("道路场景目标检测" in quote for quote in quotes)
    assert all("后来修改" not in quote for quote in quotes)

    citation_refresh = client.post(
        f"/api/v1/training-tasks/{result.task.id}/refresh-citations"
    )
    assert citation_refresh.status_code == 200, citation_refresh.text
    refreshed_evidence = citation_refresh.json()["course_evidence"]
    assert refreshed_evidence
    assert all(item["is_generation_snapshot"] for item in refreshed_evidence)
    assert all("后来修改" not in item["quote"] for item in refreshed_evidence)

    # 显式引用检查也保护没有数据库 FK 的历史 SQLite 安装。
    course_delete = client.delete(f"/api/v1/curriculum/courses/{course.id}")
    assert course_delete.status_code == 409
    assert "实训任务" in course_delete.text
    plan_delete = client.delete(f"/api/v1/curriculum/plans/{plan.id}")
    assert plan_delete.status_code == 409
    assert "实训任务" in plan_delete.text


def test_objective_skill_alias_is_normalised(approved_graph: Session) -> None:
    draft = _draft(objectives=[TaskObjective(text="掌握图像标注", skill_code="图像标注")])
    _, result = _persist(approved_graph, draft)

    assert result.task.objectives[0]["skill_code"] == "annot.image"


def test_unknown_objective_skill_is_cleared_with_warning(approved_graph: Session) -> None:
    draft = _draft(objectives=[TaskObjective(text="量子标注", skill_code="annot.quantum")])
    _, result = _persist(approved_graph, draft)

    assert result.task.objectives[0]["skill_code"] is None
    assert any("不在技能表中" in w for w in result.warnings)


def test_rubric_weight_not_100_is_warned(approved_graph: Session) -> None:
    """不强制拒绝——教师有理由用别的计分方式——但必须明确提示。"""
    draft = _draft(
        rubric=[
            RubricDimension(dimension="准确率", weight=50, levels=[RubricLevel(level="优秀", criteria="≥95%"), RubricLevel(level="合格", criteria="≥85%")]),
            RubricDimension(dimension="规范性", weight=30, levels=[RubricLevel(level="优秀", criteria="完全符合"), RubricLevel(level="合格", criteria="基本符合")]),
        ]
    )
    _, result = _persist(approved_graph, draft)
    assert any("权重合计为 80" in w for w in result.warnings)


def test_task_skill_weights_sum_to_about_one(approved_graph: Session) -> None:
    """权重用于把 rubric 得分分配回各技能，总和应接近 1。"""
    _, result = _persist(approved_graph, _draft())
    total = sum(s.weight for s in result.task.skills)
    assert total == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------- Schema
def test_step_detail_has_minimum_length() -> None:
    """步骤写得太短等于没写，学生照着做不了。"""
    with pytest.raises(ValueError):
        TaskStep(order=1, title="做标注", detail="做一下")


def test_rubric_requires_multiple_levels() -> None:
    """只有一个等级的量规无法区分水平。"""
    with pytest.raises(ValueError):
        RubricDimension(
            dimension="准确率", weight=100, levels=[RubricLevel(level="优秀", criteria="很好")]
        )


def test_draft_requires_enough_steps() -> None:
    with pytest.raises(ValueError):
        TrainingTaskDraft(
            title="太简单的任务",
            scenario="你是某公司的数据标注工程师，需要完成一批标注工作。",
            objectives=[TaskObjective(text="目标一"), TaskObjective(text="目标二")],
            steps=[TaskStep(order=1, title="做", detail="完成全部标注工作即可结束。")],
            deliverables=["结果"],
            rubric=[
                RubricDimension(dimension="质量", weight=100, levels=[RubricLevel(level="优秀", criteria="好"), RubricLevel(level="合格", criteria="还行")])
            ],
        )


# ---------------------------------------------------------------- 发布
def test_publish_marks_task(approved_graph: Session) -> None:
    service, result = _persist(approved_graph, _draft())
    task = service.publish(result.task.id, "张老师")
    approved_graph.commit()

    assert task.status is TaskStatus.PUBLISHED
    assert task.published_by == "张老师"


def test_publishing_twice_is_rejected(approved_graph: Session) -> None:
    service, result = _persist(approved_graph, _draft())
    service.publish(result.task.id, "张老师")
    approved_graph.commit()

    with pytest.raises(ConflictError):
        service.publish(result.task.id, "李老师")


def test_cannot_publish_task_without_skills(approved_graph: Session) -> None:
    """没关联技能的任务，学生做完也无法计入能力画像。"""
    node = approved_graph.get(CompetencyNode, "g1.cap1")
    # 造一个没有技能点后代的节点
    approved_graph.add(
        CompetencyNode(id="g1.unit_empty", graph_id="g1", parent_id="g1.cap1", node_type=NodeType.COMPETENCY_UNIT, name="空单元")
    )
    approved_graph.commit()
    assert node is not None

    draft = _draft(objectives=[TaskObjective(text="无技能目标")])
    service, result = _persist(approved_graph, draft, node_id="g1.unit_empty")

    assert any("未关联任何规范技能" in w for w in result.warnings)
    with pytest.raises(ValidationError, match="不能发布"):
        service.publish(result.task.id, "张老师")


def test_skills_follow_objectives_not_whole_unit(approved_graph: Session) -> None:
    """归因必须跟随学习目标，而非能力单元的全量技能。

    回归：能力单元「原始数据清洗与标注」涵盖多项技能，但一个只练图像标注的
    任务若按单元全量关联，学生会连带拿到未训练技能的加分 ——
    Phase 8 回写能力画像时这是实打实的算错。
    """
    approved_graph.add(
        CompetencyNode(
            id="g1.sp2", graph_id="g1", parent_id="g1.unit1",
            node_type=NodeType.SKILL_POINT, name="标注数据审核",
            skill_code="quality.audit", mastery_level=2,
        )
    )
    approved_graph.commit()

    # 目标只提到 annot.image，尽管单元下还有 quality.audit
    draft = _draft(objectives=[TaskObjective(text="掌握图像标注", skill_code="annot.image")])
    _, result = _persist(approved_graph, draft)

    codes = {s.skill_code for s in result.task.skills}
    assert codes == {"annot.image"}, f"不应关联未训练的技能：{codes}"


def test_falls_back_to_unit_skills_with_warning(approved_graph: Session) -> None:
    """目标未标注技能时退回单元技能，但必须提示归因偏粗。"""
    draft = _draft(objectives=[TaskObjective(text="没有编码的目标")])
    _, result = _persist(approved_graph, draft)

    codes = {s.skill_code for s in result.task.skills}
    assert "annot.image" in codes
    assert any("归因偏粗" in w for w in result.warnings)


def test_warns_when_objective_skill_outside_unit(approved_graph: Session) -> None:
    """任务偏离源能力单元必须报出来。

    实测：模型对「业务数据采集」单元生成了一个图像标注任务，还挂上
    annot.image —— 而该单元根本不含这项技能。学生做完会被记上一项
    该单元不训练的能力。根因是 prompt 的输出示例太具体被照抄，
    已改为占位式说明；这条测试守住服务端这道防线。
    """
    approved_graph.add(
        CompetencyNode(
            id="g1.unit_collect", graph_id="g1", parent_id="g1.cap1",
            node_type=NodeType.COMPETENCY_UNIT, name="业务数据采集",
        )
    )
    approved_graph.add(
        CompetencyNode(
            id="g1.sp_audit", graph_id="g1", parent_id="g1.unit_collect",
            node_type=NodeType.SKILL_POINT, name="标注数据审核",
            skill_code="quality.audit", mastery_level=2,
        )
    )
    approved_graph.commit()

    # 目标引用 annot.image，但该单元只覆盖 quality.audit
    draft = _draft(objectives=[TaskObjective(text="掌握图像标注", skill_code="annot.image")])
    _, result = _persist(approved_graph, draft, node_id="g1.unit_collect")

    assert any("不属于能力单元" in w and "疑似任务偏离源能力" in w for w in result.warnings)
