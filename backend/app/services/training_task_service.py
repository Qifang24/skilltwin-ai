"""实训任务的持久化与发布。

关键校验：
  - 任务只能从 **approved** 图谱的节点派生。draft 图谱的节点 ID 还会变，
    从它派生任务会在图谱改版后留下悬空引用。
  - 学习目标里的 skill_code 必须解析到技能表，否则任务与能力表脱钩，
    Phase 8 无法把 rubric 得分回写到学生能力画像。
  - 评分量规权重之和应为 100；不强制拒绝，但会明确警告 ——
    教师有理由用别的计分方式，不该由系统一刀切。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import GraphStatus, SKILL_BEARING_NODE_TYPES, TaskStatus
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.competency import CompetencyGraph, CompetencyNode
from app.models.curriculum import CourseSkillCoverage, CurriculumCourse, CurriculumPlan
from app.models.ontology import Skill
from app.models.training import TrainingTask, TrainingTaskSkill
from app.schemas.common import SourceRef
from app.schemas.training import TrainingTaskDraft
from app.services.skill_normalizer import SkillNormalizer

logger = get_logger(__name__)


@dataclass
class TaskPersistResult:
    task: TrainingTask
    warnings: list[str]


@dataclass
class CurriculumTaskContext:
    """经服务端校验、可安全交给任务生成器的课程上下文。"""

    plan: CurriculumPlan
    course: CurriculumCourse | None
    mappings: list[CourseSkillCoverage]
    warnings: list[str]

    def prompt_text(self) -> str:
        lines = [
            f"培养方案：{self.plan.name}",
            f"方案版本：{self.plan.version or '未标注'}",
            f"方案来源：{self.plan.source_name}",
        ]
        if self.course is None:
            lines.append("本次未指定具体课程；任务需保持与该培养方案及目标能力一致。")
            return "\n".join(lines)

        course = self.course
        lines.extend(
            [
                f"课程：{course.name}"
                + (f"（{course.course_code}）" if course.course_code else ""),
                f"课程类别：{course.category or '未标注'}；总学时：{course.total_hours if course.total_hours is not None else '未标注'}",
            ]
        )
        for label, value in (
            ("课程目标", course.objectives),
            ("课程简介", course.description),
            ("教学内容", course.teaching_content),
            ("知识点", course.knowledge_points),
            ("实践内容", course.practical_content),
            ("学习成果", course.learning_outcomes),
        ):
            if value:
                lines.append(f"{label}：{value[:1200]}")
        if course.source_quote:
            lines.append(f"课程原文：{course.source_quote[:2000]}")
        if self.mappings:
            lines.append("课程已核验的技能覆盖：")
            for mapping in self.mappings:
                lines.append(
                    f"- {mapping.skill_code}（{mapping.coverage_status}）："
                    f"{mapping.evidence_quote[:400] or '未提供映射引文'}"
                )
        return "\n".join(lines)

    def evidence_snapshot(self) -> list[dict]:
        """固化生成当时使用的课程证据，避免后续课程编辑造成依据漂移。"""
        if self.course is None:
            return []
        course = self.course
        common = {
            "plan_id": self.plan.id,
            "plan_name": self.plan.name,
            "course_id": course.id,
            "course_name": course.name,
            "is_generation_snapshot": True,
        }
        evidence: list[dict] = []
        if course.source_quote:
            evidence.append(
                {
                    **common,
                    "evidence_type": "course_source",
                    "field": "source_quote",
                    "chunk_id": course.source_chunk_id,
                    "page": course.source_page,
                    "quote": course.source_quote,
                }
            )
        for field, raw in (course.field_evidence or {}).items():
            if not isinstance(raw, dict) or not raw.get("quote"):
                continue
            evidence.append(
                {
                    **common,
                    "evidence_type": "course_field",
                    "field": field,
                    "chunk_id": raw.get("chunk_id") or course.source_chunk_id,
                    "page": raw.get("page") or course.source_page,
                    "quote": str(raw["quote"]),
                }
            )
        for mapping in self.mappings:
            if not mapping.evidence_quote:
                continue
            evidence.append(
                {
                    **common,
                    "evidence_type": "skill_coverage",
                    "skill_code": mapping.skill_code,
                    "chunk_id": mapping.source_chunk_id,
                    "page": mapping.source_page,
                    "quote": mapping.evidence_quote,
                }
            )
        return evidence


class TrainingTaskService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------ 上下文
    def node_context(self, node_id: str) -> tuple[CompetencyNode, list[str], list[tuple]]:
        """取出节点、它的路径、以及其下的技能点。"""
        node = self._db.get(CompetencyNode, node_id)
        if node is None:
            raise NotFoundError(f"未找到节点：{node_id}", detail={"node_id": node_id})

        graph = self._db.get(CompetencyGraph, node.graph_id)
        if graph is None or graph.status is not GraphStatus.APPROVED:
            raise ValidationError(
                "只能从已审核通过的图谱派生实训任务。"
                "草案图谱的节点编码仍可能变动，据此生成的任务会留下悬空引用。",
                detail={
                    "graph_id": node.graph_id,
                    "status": graph.status.value if graph else None,
                },
            )

        # 自底向上求路径
        path: list[str] = []
        cursor: CompetencyNode | None = node
        while cursor is not None:
            path.insert(0, cursor.name)
            cursor = self._db.get(CompetencyNode, cursor.parent_id) if cursor.parent_id else None

        skills: list[tuple[str, str, int | None]] = []
        for descendant in self._descendants(node):
            if descendant.skill_code:
                skill = self._db.get(Skill, descendant.skill_code)
                skills.append(
                    (
                        descendant.skill_code,
                        skill.name_zh if skill else descendant.name,
                        descendant.mastery_level,
                    )
                )

        return node, path, skills

    def _descendants(self, node: CompetencyNode) -> list[CompetencyNode]:
        out: list[CompetencyNode] = []
        for child in node.children:
            out.append(child)
            out.extend(self._descendants(child))
        return out

    def curriculum_context(
        self,
        node: CompetencyNode,
        *,
        plan_id: str | None = None,
        course_id: str | None = None,
    ) -> CurriculumTaskContext | None:
        """解析可选课程选择，并用技能映射检查它与能力节点的关联。

        ``course_id`` 可以单独提交，方案会从课程记录推导。映射缺失或暂时
        没有交集时只警告而不拒绝：导入后的人工映射可能尚未完成，但结构外键
        仍然是有效且有价值的追溯信息。
        """
        if plan_id is None and course_id is None:
            return None

        course = self._db.get(CurriculumCourse, course_id) if course_id else None
        if course_id and course is None:
            raise NotFoundError(f"未找到课程：{course_id}", detail={"course_id": course_id})

        resolved_plan_id = plan_id or (course.plan_id if course else None)
        plan = self._db.get(CurriculumPlan, resolved_plan_id) if resolved_plan_id else None
        if plan is None:
            raise NotFoundError(
                f"未找到培养方案：{resolved_plan_id}",
                detail={"plan_id": resolved_plan_id},
            )
        if course is not None and course.plan_id != plan.id:
            raise ValidationError(
                "所选课程不属于所选培养方案。",
                detail={
                    "plan_id": plan.id,
                    "course_id": course.id,
                    "course_plan_id": course.plan_id,
                },
            )

        mappings = (
            list(
                self._db.execute(
                    select(CourseSkillCoverage)
                    .where(
                        CourseSkillCoverage.course_id == course.id,
                        CourseSkillCoverage.coverage_status.in_(("covered", "partial")),
                    )
                    .order_by(CourseSkillCoverage.skill_code)
                ).scalars()
            )
            if course
            else []
        )
        warnings: list[str] = []
        node_skill_codes = {
            item.skill_code for item in self._descendants(node) if item.skill_code
        }
        mapped_codes = {item.skill_code for item in mappings}
        if course and not mappings:
            warnings.append(
                f"课程「{course.name}」尚无已确认的技能覆盖映射；已保留课程关联，"
                "请教师核对任务目标后再发布"
            )
        elif course and node_skill_codes and not (node_skill_codes & mapped_codes):
            warnings.append(
                f"课程「{course.name}」的技能覆盖与能力单元「{node.name}」暂无交集；"
                "已保留两端证据，请教师确认课程选择是否合适"
            )

        return CurriculumTaskContext(
            plan=plan, course=course, mappings=mappings, warnings=warnings
        )

    # ------------------------------------------------------------ 持久化
    def persist(
        self,
        *,
        node: CompetencyNode,
        draft: TrainingTaskDraft,
        sources: list[SourceRef],
        generation_run_id: str | None = None,
        curriculum: CurriculumTaskContext | None = None,
    ) -> TaskPersistResult:
        graph = self._db.get(CompetencyGraph, node.graph_id)
        warnings: list[str] = list(curriculum.warnings) if curriculum else []
        normalizer = SkillNormalizer(self._db)

        # 该能力单元实际覆盖的技能及其掌握程度要求。
        # 目标若引用了单元之外的技能，属于跑题：学生做完这个任务，
        # 得分会被记到一项该单元根本不训练的能力上。
        unit_skills: dict[str, int | None] = {
            d.skill_code: d.mastery_level
            for d in self._descendants(node)
            if d.skill_code and d.node_type in SKILL_BEARING_NODE_TYPES
        }
        unit_skill_codes = set(unit_skills)

        # ---- 学习目标的技能编码归一 ----
        objectives: list[dict] = []
        objective_skills: set[str] = set()
        for objective in draft.objectives:
            resolved = None
            if objective.skill_code:
                resolved = normalizer.resolve(objective.skill_code)
                if resolved is None:
                    warnings.append(
                        f"学习目标「{objective.text}」的技能编码 "
                        f"{objective.skill_code!r} 不在技能表中，已置空"
                    )
                elif unit_skill_codes and resolved not in unit_skill_codes:
                    warnings.append(
                        f"学习目标「{objective.text}」引用的技能 {resolved} "
                        f"不属于能力单元「{node.name}」（该单元覆盖 "
                        f"{sorted(unit_skill_codes)}），疑似任务偏离源能力，请教师核对"
                    )
                    objective_skills.add(resolved)
                else:
                    objective_skills.add(resolved)
            objectives.append({"text": objective.text, "skill_code": resolved})

        # ---- 评分权重校验 ----
        weight_total = sum(d.weight for d in draft.rubric)
        if weight_total != 100:
            warnings.append(
                f"评分量规权重合计为 {weight_total}，通常应为 100，请教师确认"
            )

        task_id = f"task_{uuid.uuid4().hex[:16]}"
        task = TrainingTask(
            id=task_id,
            job_id=graph.job_id,
            source_node_id=node.id,
            plan_id=curriculum.plan.id if curriculum else None,
            course_id=curriculum.course.id if curriculum and curriculum.course else None,
            title=draft.title,
            scenario=draft.scenario,
            difficulty=draft.difficulty,
            est_minutes=draft.est_minutes,
            objectives=objectives,
            steps=[s.model_dump() for s in sorted(draft.steps, key=lambda x: x.order)],
            deliverables=list(draft.deliverables),
            rubric=[d.model_dump() for d in draft.rubric],
            common_mistakes=[m.model_dump() for m in draft.common_mistakes],
            extensions=list(draft.extensions),
            safety_notes=draft.safety_notes,
            citations=[
                {
                    "chunk_id": s.chunk_id,
                    "source_name": s.source_name,
                    "page": s.page,
                    "section": s.section,
                    "quote": s.quote,
                }
                for s in sources
            ]
            + (curriculum.evidence_snapshot() if curriculum else []),
            generation_run_id=generation_run_id,
            status=TaskStatus.DRAFT,
        )
        self._db.add(task)
        self._db.flush()

        # ---- 关联技能 ----
        # 以**学习目标实际训练的技能**为准，而不是该能力单元覆盖的全部技能。
        # 二者常常不同：能力单元「原始数据清洗与标注」涵盖文本/视觉/规范三项，
        # 但一个具体任务可能只练图像标注。若按单元全量关联，
        # 学生做完图像标注任务会连带拿到文本标注的能力加分 ——
        # Phase 8 回写能力画像时这就是实打实的算错。
        if objective_skills:
            trained = objective_skills
        else:
            # 目标里一个技能都没标注时，退回单元技能并提示 —— 这时归因必然偏粗
            trained = set(unit_skill_codes)
            if trained:
                warnings.append(
                    "学习目标未标注技能编码，已按该能力单元覆盖的全部技能关联，"
                    "归因偏粗，建议教师核对后调整"
                )

        if not trained:
            warnings.append("该任务未关联任何规范技能，完成后无法回写学生能力画像")

        weight = round(1.0 / len(trained), 4) if trained else 0.0
        for code in sorted(trained):
            self._db.add(
                TrainingTaskSkill(
                    task_id=task_id,
                    skill_code=code,
                    weight=weight,
                    # 掌握程度取自图谱，没有对应节点时留空而不臆测
                    target_level=unit_skills.get(code),
                )
            )
        self._db.flush()

        logger.info(
            "实训任务已生成",
            extra={
                "task_id": task_id,
                "node_id": node.id,
                "skills": len(trained),
                "warnings": len(warnings),
            },
        )
        return TaskPersistResult(task=task, warnings=warnings)

    # ------------------------------------------------------------ 发布
    def publish(self, task_id: str, published_by: str) -> TrainingTask:
        task = self._db.get(TrainingTask, task_id)
        if task is None:
            raise NotFoundError(f"未找到任务：{task_id}", detail={"task_id": task_id})
        if task.status is TaskStatus.PUBLISHED:
            raise ConflictError("该任务已发布")

        if not task.skills:
            raise ValidationError(
                "任务未关联任何规范技能，发布后学生完成也无法计入能力画像，不能发布",
                detail={"task_id": task_id},
            )

        task.status = TaskStatus.PUBLISHED
        task.published_by = published_by
        self._db.flush()
        logger.info("实训任务已发布", extra={"task_id": task_id, "by": published_by})
        return task

    def list_for_job(self, job_id: str, status: TaskStatus | None = None):
        stmt = select(TrainingTask).where(TrainingTask.job_id == job_id)
        if status:
            stmt = stmt.where(TrainingTask.status == status)
        return self._db.execute(stmt.order_by(TrainingTask.created_at.desc())).scalars().all()
