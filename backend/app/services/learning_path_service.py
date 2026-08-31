"""学习路径的组装与持久化。

职责边界：
  本文件负责**顺序**（调用 path_ordering）与**资源挂接**（找已发布的实训任务）；
  LearningPathAgent 只负责文案。模型给的 order_index 一律以算法结果为准 ——
  若模型擅自改序，这里会忽略并记录警告。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from app.agents.learning_path import LearningPathAgent, PathCopyInput
from app.core.db import utcnow
from app.core.enums import (
    AssessmentStatus,
    AssessmentType,
    EvidenceSufficiency,
    SKILL_BEARING_NODE_TYPES,
    EdgeRelation,
    GraphStatus,
    PathItemType,
    PathStatus,
    TaskStatus,
)
from app.core.errors import ConflictError, NotFoundError, SkillTwinError, ValidationError
from app.core.logging import get_logger
from app.models.competency import CompetencyEdge, CompetencyGraph, CompetencyNode
from app.models.learning import (
    LearningPath,
    LearningPathActivity,
    LearningPathItem,
    LearningPathPhase,
)
from app.models.ontology import Job, Skill
from app.models.student import Assessment, SkillProfile, Student
from app.models.training import TrainingTask, TrainingTaskSkill
from app.schemas.common import SourceRef
from app.services.assessment_service import AssessmentService
from app.services.competency_graph_service import CompetencyGraphService
from app.services.path_ordering import (
    OrderingResult,
    merge_small_layers,
    order_by_prerequisites,
)
from app.services.scoring import SkillEstimate, SkillGap, compute_gaps

logger = get_logger(__name__)

#: 差距小于此值视为已基本达标，不纳入学习路径
GAP_THRESHOLD = 5.0


@dataclass
class PathBuildResult:
    path: LearningPath
    warnings: list[str]
    ordering: OrderingResult


@dataclass
class PathGenerationResult:
    path: LearningPath
    warnings: list[str]
    sources: list[SourceRef]
    reasoning_summary: str
    confidence: float
    evidence_sufficiency: EvidenceSufficiency
    ai_generated: bool


@dataclass
class PathAdaptationResult:
    linked_item_id: str | None = None
    archived_path_id: str | None = None
    new_path_id: str | None = None
    recalculated: bool = False
    message: str = ""
    warnings: list[str] | None = None


class LearningPathService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------ 前置依赖
    def prereq_pairs(self, graph_id: str) -> list[tuple[str, str]]:
        """把图谱里的 prereq 边翻译成技能编码对。

        边存在节点之间，但排序是按技能做的 —— 这里做一次映射。
        """
        edges = (
            self._db.execute(
                select(CompetencyEdge).where(
                    CompetencyEdge.graph_id == graph_id,
                    CompetencyEdge.relation == EdgeRelation.PREREQ,
                )
            )
            .scalars()
            .all()
        )
        if not edges:
            return []

        node_ids = {e.from_node_id for e in edges} | {e.to_node_id for e in edges}
        nodes = {
            n.id: n
            for n in self._db.execute(
                select(CompetencyNode).where(CompetencyNode.id.in_(node_ids))
            ).scalars()
        }

        pairs: list[tuple[str, str]] = []
        for edge in edges:
            source = nodes.get(edge.from_node_id)
            target = nodes.get(edge.to_node_id)
            if source and target and source.skill_code and target.skill_code:
                pairs.append((source.skill_code, target.skill_code))
        return pairs

    # ------------------------------------------------------ 排序
    def plan(
        self, gaps: list[SkillGap], graph_id: str, max_phases: int = 4
    ) -> OrderingResult:
        """确定性排序。**不经模型。**"""
        # 没测过不等于能力为零。compute_gaps 为了保留目标维度会把其 current
        # 写为 0，但 evidence_count 同时为 0；这类项只能提示补测，不能据此排序。
        untested = [
            g for g in gaps if g.gap > GAP_THRESHOLD and g.evidence_count <= 0
        ]
        pending = [
            g for g in gaps if g.gap > GAP_THRESHOLD and g.evidence_count > 0
        ]
        warnings: list[str] = []
        if untested:
            warnings.append(
                f"{len(untested)} 项目标技能尚未被测评，未纳入学习阶段；"
                "请补充题目并复测后再安排。"
            )
        preliminary = [g for g in pending if not g.reliable]
        if preliminary:
            warnings.append(
                f"{len(preliminary)} 项技能已有作答但证据仍不足，"
                "当前路径仅用于初步定位，建议增加题量后复测。"
            )
        if not pending:
            message = (
                "暂无已测评且需要补齐的技能，无法生成可执行学习路径"
                if untested
                else "全部已测评技能均已达标，无需安排学习路径"
            )
            return OrderingResult(warnings=[*warnings, message])

        prereqs = self.prereq_pairs(graph_id)
        ordering = order_by_prerequisites(pending, prereqs)
        ordering.warnings = [*warnings, *ordering.warnings]
        if not prereqs:
            ordering.warnings.append(
                "该图谱尚未标注技能前置依赖，阶段划分仅按能力差距降序。"
                "运行 scripts/build_prerequisites.py 可补充依赖关系。"
            )
            ordering.method = "gap_desc_only"
        return merge_small_layers(ordering, max_phases=max_phases)

    # ------------------------------------------------------ 端到端生成
    def generate_for_student(
        self,
        *,
        student_id: str,
        job_id: str | None = None,
        max_phases: int = 4,
        agent: LearningPathAgent | None = None,
    ) -> PathGenerationResult:
        """从学生画像生成并持久化一条路径；事务提交由 API 调用方负责。"""
        student = self._db.get(Student, student_id)
        if student is None:
            raise NotFoundError(
                f"未找到学生：{student_id}", detail={"student_id": student_id}
            )

        target_job_id = job_id or student.target_job_id
        if not target_job_id:
            raise ValidationError("请指定目标岗位，或先为学生设置 target_job_id")

        job = self._db.get(Job, target_job_id)
        if job is None:
            raise NotFoundError(
                f"未找到岗位：{target_job_id}", detail={"job_id": target_job_id}
            )

        graph = self.approved_graph(target_job_id)
        profile = AssessmentService(self._db).latest_profile(
            student.id, target_job_id
        )
        if profile is None:
            raise ValidationError(
                "该学生尚未完成目标岗位的诊断测评，无法生成个性化学习路径",
                detail={"student_id": student.id, "job_id": target_job_id},
            )

        estimates = {
            entry.skill_code: SkillEstimate(
                skill_code=entry.skill_code,
                score=entry.score,
                score_low=entry.score_low,
                score_high=entry.score_high,
                confidence=entry.confidence,
                evidence_count=entry.evidence_count,
                method=entry.method,
            )
            for entry in profile.entries
        }
        target_vector = CompetencyGraphService(self._db).target_skill_vector(graph)
        gaps = compute_gaps(target_vector, estimates)
        ordering = self.plan(gaps, graph.id, max_phases=max_phases)
        if not ordering.layers:
            raise ValidationError(
                "当前画像无法生成可执行学习路径",
                detail={
                    "student_id": student.id,
                    "job_id": target_job_id,
                    "warnings": ordering.warnings,
                },
            )

        phases = []
        for layer in ordering.layers:
            skills = []
            for gap in layer.gaps:
                skill = self._db.get(Skill, gap.skill_code)
                skills.append(
                    (
                        skill.name_zh if skill else gap.skill_code,
                        gap.gap,
                        gap.reliable,
                    )
                )
            phases.append((layer.index, skills, layer.note))

        envelope = (agent or LearningPathAgent()).run(
            self._db,
            PathCopyInput(
                student_name=student.display_name,
                job_name=job.name,
                ordering_method=ordering.method,
                phases=phases,
            ),
        )
        built = self.persist(
            student=student,
            job_id=target_job_id,
            graph_id=graph.id,
            profile=profile,
            ordering=ordering,
            copy=envelope.result,
            generation_run_id=envelope.llm_run_id,
        )
        combined_warnings = [*envelope.warnings, *built.warnings]
        built.path.warnings = combined_warnings
        self._db.flush()
        return PathGenerationResult(
            path=built.path,
            warnings=combined_warnings,
            sources=envelope.sources,
            reasoning_summary=envelope.reasoning_summary,
            confidence=envelope.confidence,
            evidence_sufficiency=envelope.evidence_sufficiency,
            ai_generated=envelope.ai_generated,
        )

    # ------------------------------------------------------ 资源挂接
    def _tasks_for_skill(self, job_id: str, skill_code: str) -> list[TrainingTask]:
        """找已发布且训练该技能的实训任务。

        只挂 **published** 的任务 —— 草案还没经教师确认，不该推给学生。
        找不到就不挂，绝不编造一个不存在的资源。
        """
        return list(
            self._db.execute(
                select(TrainingTask)
                .join(TrainingTaskSkill)
                .where(
                    TrainingTask.job_id == job_id,
                    TrainingTask.status == TaskStatus.PUBLISHED,
                    TrainingTaskSkill.skill_code == skill_code,
                )
                .options(selectinload(TrainingTask.skills))
            )
            .scalars()
            .unique()
        )

    # ------------------------------------------------------ 持久化
    def persist(
        self,
        *,
        student: Student,
        job_id: str,
        graph_id: str,
        profile: SkillProfile | None,
        ordering: OrderingResult,
        copy,  # LearningPathCopy
        generation_run_id: str | None = None,
    ) -> PathBuildResult:
        warnings = list(ordering.warnings)

        # 模型可能擅自改序或增删阶段，一律以算法结果为准
        copy_by_index = {phase.order_index: phase for phase in copy.phases}
        if len(copy.phases) != len(ordering.layers):
            warnings.append(
                f"模型返回 {len(copy.phases)} 个阶段，算法划分为 "
                f"{len(ordering.layers)} 个，已按算法结果为准"
            )

        # 同一学生、同一岗位只保留一条当前路径。重新生成不是覆盖历史，
        # 而是把旧版本归档后新建版本，便于比赛演示能力变化轨迹。
        self.archive_current_paths(student.id, job_id)

        path = LearningPath(
            id=f"path_{uuid.uuid4().hex[:16]}",
            student_id=student.id,
            job_id=job_id,
            profile_id=profile.id if profile else None,
            graph_id=graph_id,
            title=copy.title,
            rationale=copy.rationale,
            ordering_method=ordering.method,
            warnings=warnings,
            generation_run_id=generation_run_id,
        )
        self._db.add(path)
        self._db.flush()

        for layer in ordering.layers:
            text = copy_by_index.get(layer.index)
            skill_codes = [g.skill_code for g in layer.gaps]

            phase = LearningPathPhase(
                id=f"phase_{uuid.uuid4().hex[:14]}",
                path_id=path.id,
                order_index=layer.index,
                title=text.title if text else f"第 {layer.index + 1} 阶段",
                description=text.description if text else None,
                target_skill_codes=skill_codes,
                est_hours=text.est_hours if text else None,
                ordering_note=layer.note,
            )
            self._db.add(phase)
            self._db.flush()

            order = 0
            if text and text.suggestions:
                self._db.add(
                    LearningPathItem(
                        id=f"item_{uuid.uuid4().hex[:14]}",
                        phase_id=phase.id,
                        order_index=order,
                        item_type=PathItemType.PRACTICE,
                        title="本阶段行动建议",
                        description="\n".join(
                            f"{index}. {suggestion}"
                            for index, suggestion in enumerate(
                                text.suggestions, start=1
                            )
                        ),
                        extra={"suggestions": list(text.suggestions)},
                    )
                )
                order += 1
            for gap in layer.gaps:
                skill = self._db.get(Skill, gap.skill_code)
                name = skill.name_zh if skill else gap.skill_code

                # 知识学习项
                self._db.add(
                    LearningPathItem(
                        id=f"item_{uuid.uuid4().hex[:14]}",
                        phase_id=phase.id,
                        order_index=order,
                        item_type=PathItemType.KNOWLEDGE,
                        title=f"学习：{name}",
                        description=(
                            f"当前 {gap.current_score:.0f} 分，目标 "
                            f"{gap.target_score:.0f} 分，差距 {gap.gap:.0f}"
                            + ("（该项证据不足，建议先补测）" if not gap.reliable else "")
                        ),
                        skill_code=gap.skill_code,
                        extra={"gap": gap.gap, "reliable": gap.reliable},
                    )
                )
                order += 1

                # 有已发布的实训任务就挂上，没有就不挂
                for task in self._tasks_for_skill(job_id, gap.skill_code)[:2]:
                    self._db.add(
                        LearningPathItem(
                            id=f"item_{uuid.uuid4().hex[:14]}",
                            phase_id=phase.id,
                            order_index=order,
                            item_type=PathItemType.TASK,
                            title=task.title,
                            description=f"实训任务 · 建议用时 {task.est_minutes or '—'} 分钟",
                            ref_id=task.id,
                            skill_code=gap.skill_code,
                        )
                    )
                    order += 1

            # 每阶段末尾加一次复测：能力更新才能驱动路径调整，闭环靠它成立
            self._db.add(
                LearningPathItem(
                    id=f"item_{uuid.uuid4().hex[:14]}",
                    phase_id=phase.id,
                    order_index=order,
                    item_type=PathItemType.ASSESSMENT,
                    title="阶段复测",
                    description="重新测评本阶段技能，更新能力画像并调整后续路径",
                    extra={"skill_codes": skill_codes},
                )
            )

        self._db.flush()
        logger.info(
            "学习路径已生成",
            extra={
                "path_id": path.id,
                "phases": len(ordering.layers),
                "method": ordering.method,
            },
        )
        return PathBuildResult(path=path, warnings=warnings, ordering=ordering)

    # ------------------------------------------------------ 学习进度与活动
    def archive_current_paths(self, student_id: str, job_id: str) -> list[str]:
        paths = list(
            self._db.execute(
                select(LearningPath).where(
                    LearningPath.student_id == student_id,
                    LearningPath.job_id == job_id,
                    LearningPath.status != PathStatus.ARCHIVED,
                )
            ).scalars()
        )
        for path in paths:
            path.status = PathStatus.ARCHIVED
        if paths:
            self._db.flush()
        return [path.id for path in paths]

    def _path_containing_item(
        self, student_id: str, item_id: str
    ) -> tuple[LearningPath, LearningPathItem]:
        path = (
            self._db.execute(
                select(LearningPath)
                .join(LearningPathPhase)
                .join(LearningPathItem)
                .options(
                    selectinload(LearningPath.phases)
                    .selectinload(LearningPathPhase.items)
                    .selectinload(LearningPathItem.activities)
                )
                .where(
                    LearningPath.student_id == student_id,
                    LearningPathItem.id == item_id,
                )
            )
            .scalars()
            .unique()
            .first()
        )
        if path is None:
            raise NotFoundError(
                f"未找到学习项：{item_id}",
                detail={"student_id": student_id, "item_id": item_id},
            )
        item = next(
            item
            for phase in path.phases
            for item in phase.items
            if item.id == item_id
        )
        return path, item

    def _record_activity(
        self,
        *,
        item: LearningPathItem,
        student_id: str,
        action: str,
        previous_status: PathStatus | None = None,
        new_status: PathStatus | None = None,
        ref_type: str | None = None,
        ref_id: str | None = None,
        note: str | None = None,
    ) -> LearningPathActivity:
        activity = LearningPathActivity(
            id=f"act_{uuid.uuid4().hex[:16]}",
            item=item,
            student_id=student_id,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self._db.add(activity)
        return activity

    @staticmethod
    def _sync_statuses(path: LearningPath) -> None:
        terminal = {PathStatus.COMPLETED, PathStatus.SKIPPED}
        for phase in path.phases:
            statuses = [item.status for item in phase.items]
            if statuses and all(status in terminal for status in statuses):
                phase.status = (
                    PathStatus.SKIPPED
                    if all(status is PathStatus.SKIPPED for status in statuses)
                    else PathStatus.COMPLETED
                )
            else:
                phase.status = PathStatus.ACTIVE

        if path.status is not PathStatus.ARCHIVED:
            path.status = (
                PathStatus.COMPLETED
                if path.phases
                and all(phase.status in terminal for phase in path.phases)
                else PathStatus.ACTIVE
            )

    def update_item_status(
        self,
        *,
        student_id: str,
        item_id: str,
        status: PathStatus,
        note: str | None = None,
        allow_assessment_completion: bool = False,
        action: str = "status_changed",
        ref_type: str | None = None,
        ref_id: str | None = None,
    ) -> LearningPath:
        if status not in {
            PathStatus.ACTIVE,
            PathStatus.COMPLETED,
            PathStatus.SKIPPED,
        }:
            raise ValidationError("学习项只支持进行中、已完成或已跳过状态")

        path, item = self._path_containing_item(student_id, item_id)
        if path.status is PathStatus.ARCHIVED:
            raise ConflictError("已归档学习路径不可修改")
        if (
            item.item_type is PathItemType.ASSESSMENT
            and status is PathStatus.COMPLETED
            and not allow_assessment_completion
        ):
            raise ConflictError("阶段复测必须完成判分后由系统自动标记，不能手动完成")

        previous = item.status
        if previous is status:
            return path

        item.status = status
        item.completed_at = utcnow() if status is PathStatus.COMPLETED else None
        self._record_activity(
            item=item,
            student_id=student_id,
            action=action,
            previous_status=previous,
            new_status=status,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
        )
        self._sync_statuses(path)
        self._db.flush()
        return path

    def start_retest(
        self, *, student_id: str, item_id: str, item_count: int
    ):
        path, item = self._path_containing_item(student_id, item_id)
        if path.status is PathStatus.ARCHIVED:
            raise ConflictError("已归档学习路径不能开始复测")
        if item.item_type is not PathItemType.ASSESSMENT:
            raise ValidationError("只有阶段复测学习项可以创建复测")
        if item.status is PathStatus.COMPLETED:
            raise ConflictError("该阶段复测已经完成")

        for activity in reversed(item.activities):
            if activity.action != "assessment_started" or not activity.ref_id:
                continue
            existing = self._db.get(Assessment, activity.ref_id)
            if existing and existing.status is AssessmentStatus.IN_PROGRESS:
                raise ConflictError(
                    "该学习项已有未完成的复测",
                    detail={"assessment_id": existing.id},
                )

        student = self._db.get(Student, student_id)
        if student is None:  # pragma: no cover - path 外键已保证
            raise NotFoundError(f"未找到学生：{student_id}")
        started = AssessmentService(self._db).start(
            student=student,
            job_id=path.job_id,
            item_count=item_count,
            assessment_type=AssessmentType.RETEST,
        )
        self._record_activity(
            item=item,
            student_id=student_id,
            action="assessment_started",
            previous_status=item.status,
            new_status=item.status,
            ref_type="assessment",
            ref_id=started.assessment.id,
            note="从个性化学习路径发起阶段复测",
        )
        self._db.flush()
        return started

    def adapt_after_scored_assessment(
        self, assessment_id: str
    ) -> PathAdaptationResult | None:
        link = (
            self._db.execute(
                select(LearningPathActivity)
                .where(
                    LearningPathActivity.action == "assessment_started",
                    LearningPathActivity.ref_type == "assessment",
                    LearningPathActivity.ref_id == assessment_id,
                )
                .order_by(LearningPathActivity.created_at.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if link is None:
            return None

        assessment = self._db.get(Assessment, assessment_id)
        if assessment is None:  # pragma: no cover - submit 已验证
            return None
        path, _ = self._path_containing_item(assessment.student_id, link.item_id)
        old_path_id = path.id
        max_phases = max(1, min(len(path.phases), 8))

        self.update_item_status(
            student_id=assessment.student_id,
            item_id=link.item_id,
            status=PathStatus.COMPLETED,
            allow_assessment_completion=True,
            action="assessment_scored",
            ref_type="assessment",
            ref_id=assessment.id,
            note="复测已判分并生成新的能力画像",
        )
        self.archive_current_paths(assessment.student_id, assessment.job_id)

        try:
            generated = self.generate_for_student(
                student_id=assessment.student_id,
                job_id=assessment.job_id,
                max_phases=max_phases,
            )
        except SkillTwinError as exc:
            logger.warning(
                "复测后学习路径自动重算未生成新路径",
                extra={"assessment_id": assessment.id, "reason": exc.message},
            )
            detail_warnings = exc.detail.get("warnings", [])
            return PathAdaptationResult(
                linked_item_id=link.item_id,
                archived_path_id=old_path_id,
                recalculated=False,
                message=(
                    "复测结果已更新能力画像，旧路径已归档；"
                    f"暂未生成新路径：{exc.message}"
                ),
                warnings=list(detail_warnings),
            )

        return PathAdaptationResult(
            linked_item_id=link.item_id,
            archived_path_id=old_path_id,
            new_path_id=generated.path.id,
            recalculated=True,
            message="复测结果已更新能力画像，旧路径已归档并生成新路径",
            warnings=generated.warnings,
        )

    # ------------------------------------------------------ 查询
    def latest_path(
        self, student_id: str, job_id: str | None = None
    ) -> LearningPath | None:
        filters = [LearningPath.student_id == student_id]
        if job_id:
            filters.append(LearningPath.job_id == job_id)
        return (
            self._db.execute(
                select(LearningPath)
                .options(
                    selectinload(LearningPath.phases).selectinload(
                        LearningPathPhase.items
                    ).selectinload(
                        LearningPathItem.activities
                    )
                )
                .where(*filters)
                .order_by(
                    case(
                        (LearningPath.status == PathStatus.ACTIVE, 0),
                        (LearningPath.status == PathStatus.COMPLETED, 1),
                        else_=2,
                    ),
                    LearningPath.created_at.desc(),
                    LearningPath.id.desc(),
                )
                .limit(1)
            )
            .scalars()
            .first()
        )

    def approved_graph(self, job_id: str) -> CompetencyGraph:
        graph = self._db.execute(
            select(CompetencyGraph)
            .options(selectinload(CompetencyGraph.nodes))
            .where(
                CompetencyGraph.job_id == job_id,
                CompetencyGraph.status == GraphStatus.APPROVED,
            )
        ).scalars().first()
        if graph is None:
            raise ValidationError(
                f"岗位 {job_id} 尚无已审核的能力图谱，无法确定学习目标",
                detail={"job_id": job_id},
            )
        return graph
