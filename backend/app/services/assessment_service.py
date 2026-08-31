"""测评流程与能力画像生成。

判分与能力估计**全部是确定性计算**（见 services/scoring.py），
模型只参与命题。这条边界不能模糊：学生的能力值若由模型随口给出，
自适应学习闭环就失去了意义。
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import utcnow
from app.core.enums import (
    OBJECTIVE_ITEM_TYPES,
    AssessmentStatus,
    AssessmentType,
    ProfileSource,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.student import (
    Assessment,
    AssessmentItem,
    AssessmentItemSkill,
    AssessmentResponse,
    SkillProfile,
    SkillProfileEntry,
    Student,
)
from app.services.scoring import CONFIDENCE_RELIABLE, SkillEstimate, aggregate_responses

logger = get_logger(__name__)

#: 每个技能至少要有这么多题，估计才勉强有意义。低于此值会在 notes 中提示。
MIN_ITEMS_PER_SKILL = 3


@dataclass
class ScoreResult:
    profile: SkillProfile
    correct_count: int
    total_count: int
    notes: list[str]
    updated_skill_codes: list[str]
    inherited_skill_codes: list[str]


@dataclass
class StartResult:
    assessment: Assessment
    #: 开考前就该说清这份卷子能得出多可信的结论
    notes: list[str]


def grade_objective(answer_key: list[str], response: list[str]) -> float:
    """客观题判分：完全一致得 1 分，否则 0 分。

    多选不给部分分 —— 部分分会让能力估计的「一题一证据」假设失效，
    且高职测评实践中多选通常也是全对才得分。
    """
    return 1.0 if sorted(answer_key) == sorted(response) else 0.0


class AssessmentService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------ 组卷
    def start(
        self,
        *,
        student: Student,
        job_id: str,
        item_count: int,
        assessment_type: AssessmentType = AssessmentType.DIAGNOSTIC,
    ) -> StartResult:
        items = self._select_items(job_id, item_count)
        if not items:
            raise ValidationError(
                "该岗位题库为空，无法开始测评。"
                "请先运行 scripts/generate_items.py 生成题库。",
                detail={"job_id": job_id},
            )

        # 开考前就把统计效力说清楚。等交完卷才提示「14 项全部不可信」，
        # 学生已经白做了 16 道题 —— 该说的话要说在前面。
        covered = {link.skill_code for item in items for link in item.skills}
        notes: list[str] = []
        if covered:
            per_skill = len(items) / len(covered)
            if per_skill < MIN_ITEMS_PER_SKILL:
                needed = MIN_ITEMS_PER_SKILL * len(covered)
                notes.append(
                    f"本卷 {len(items)} 题覆盖 {len(covered)} 项技能，"
                    f"平均每项约 {per_skill:.1f} 题。能力估计需要每项至少 "
                    f"{MIN_ITEMS_PER_SKILL} 题才可信，本次结果将主要用于"
                    f"初步定位薄弱方向，不宜作为精确评价。"
                    f"如需可信结论，建议出到 {needed} 题以上。"
                )

        assessment = Assessment(
            id=f"asmt_{uuid.uuid4().hex[:16]}",
            student_id=student.id,
            job_id=job_id,
            type=assessment_type,
            status=AssessmentStatus.IN_PROGRESS,
            started_at=utcnow(),
        )
        self._db.add(assessment)
        self._db.flush()

        # 预建作答记录，锁定本次卷面 —— 否则题库变动会让同一份卷子前后不一致
        for item in items:
            self._db.add(
                AssessmentResponse(assessment_id=assessment.id, item_id=item.id)
            )
        self._db.flush()

        logger.info(
            "测评已开始",
            extra={
                "assessment_id": assessment.id,
                "items": len(items),
                "skills": len(covered),
            },
        )
        return StartResult(assessment=assessment, notes=notes)

    def _select_items(self, job_id: str, count: int) -> list[AssessmentItem]:
        """组卷：尽量让每个技能都被覆盖到，而不是随机抽。

        随机抽题会让某些技能一题没有、某些技能五题 ——
        前者能力值无从估计，后者浪费学生时间。
        """
        items = (
            self._db.execute(
                select(AssessmentItem)
                .options(selectinload(AssessmentItem.skills))
                .where(
                    AssessmentItem.job_id == job_id,
                    AssessmentItem.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )
        if not items:
            return []

        by_skill: dict[str, list[AssessmentItem]] = {}
        for item in items:
            for link in item.skills:
                by_skill.setdefault(link.skill_code, []).append(item)

        rng = random.Random(0xC0FFEE)  # 固定种子：同一题库的组卷可复现
        for pool in by_skill.values():
            rng.shuffle(pool)

        selected: list[AssessmentItem] = []
        seen: set[str] = set()

        # 轮转各技能取题，保证覆盖面
        cursors = {code: 0 for code in by_skill}
        while len(selected) < count:
            progressed = False
            for code, pool in by_skill.items():
                if len(selected) >= count:
                    break
                index = cursors[code]
                while index < len(pool) and pool[index].id in seen:
                    index += 1
                cursors[code] = index
                if index < len(pool):
                    selected.append(pool[index])
                    seen.add(pool[index].id)
                    cursors[code] = index + 1
                    progressed = True
            if not progressed:
                break  # 题库已取尽

        return selected

    # ------------------------------------------------------------ 判分
    def submit(
        self, assessment_id: str, responses: dict[str, list[str]]
    ) -> ScoreResult:
        assessment = self._db.execute(
            select(Assessment)
            .options(selectinload(Assessment.responses))
            .where(Assessment.id == assessment_id)
        ).scalar_one_or_none()
        if assessment is None:
            raise NotFoundError(
                f"未找到测评：{assessment_id}", detail={"assessment_id": assessment_id}
            )
        if assessment.status is AssessmentStatus.SCORED:
            raise ConflictError("该测评已判分，不能重复提交")

        graded: list[tuple[str, float, float]] = []
        correct_count = 0
        skill_item_counts: dict[str, int] = {}

        for record in assessment.responses:
            item = self._db.get(AssessmentItem, record.item_id)
            if item is None:
                continue

            answer = responses.get(record.item_id, [])
            record.response = list(answer)
            record.answered_at = utcnow()

            if item.item_type in OBJECTIVE_ITEM_TYPES:
                score = grade_objective(item.answer_key, answer)
            else:
                # 主观题当前不参与自动判分，留空由教师评阅
                record.is_correct = None
                record.score = None
                continue

            record.score = score
            record.is_correct = score >= 1.0
            if record.is_correct:
                correct_count += 1

            for link in item.skills:
                graded.append((link.skill_code, score, link.weight))
                skill_item_counts[link.skill_code] = (
                    skill_item_counts.get(link.skill_code, 0) + 1
                )

        assessment.status = AssessmentStatus.SCORED
        assessment.submitted_at = utcnow()

        current_estimates = aggregate_responses(graded)
        estimates, inherited_codes = self._merge_previous_snapshot(
            student_id=assessment.student_id,
            job_id=assessment.job_id,
            current=current_estimates,
        )
        source = self._profile_source(
            assessment.type, inherited=bool(inherited_codes)
        )
        profile = self._persist_profile(
            student_id=assessment.student_id,
            job_id=assessment.job_id,
            assessment_id=assessment.id,
            estimates=estimates,
            source=source,
        )

        notes = self._build_notes(current_estimates, skill_item_counts)
        if inherited_codes:
            notes.append(
                f"本次复测覆盖 {len(current_estimates)} 项技能；另有 "
                f"{len(inherited_codes)} 项沿用上一份同岗位画像。"
                "沿用项未重新测量，证据条数与置信度均未增加。"
            )
        self._db.flush()

        logger.info(
            "测评已判分",
            extra={
                "assessment_id": assessment_id,
                "correct": correct_count,
                "skills": len(estimates),
            },
        )
        return ScoreResult(
            profile=profile,
            correct_count=correct_count,
            total_count=len(assessment.responses),
            notes=notes,
            updated_skill_codes=sorted(current_estimates),
            inherited_skill_codes=inherited_codes,
        )

    def _merge_previous_snapshot(
        self,
        *,
        student_id: str,
        job_id: str,
        current: dict[str, SkillEstimate],
    ) -> tuple[dict[str, SkillEstimate], list[str]]:
        """用本次结果覆盖同岗位旧快照，未复测维度原样继承。

        这里刻意不把两次分数做平均：当前表只保存区间与有效题数，没有足够
        统计量恢复联合分布，硬平均会制造虚假精度。继承项的 evidence_count
        与 confidence 保持原值，明确表示本次没有增加新证据。
        """
        previous = self.latest_profile(student_id, job_id)
        if previous is None:
            return dict(current), []

        merged = {
            entry.skill_code: SkillEstimate(
                skill_code=entry.skill_code,
                score=entry.score,
                score_low=entry.score_low,
                score_high=entry.score_high,
                confidence=entry.confidence,
                evidence_count=entry.evidence_count,
                method=entry.method,
            )
            for entry in previous.entries
        }
        inherited = sorted(set(merged) - set(current))
        merged.update(current)
        return merged, inherited

    @staticmethod
    def _profile_source(
        assessment_type: AssessmentType, *, inherited: bool
    ) -> ProfileSource:
        if inherited or assessment_type is AssessmentType.RETEST:
            return ProfileSource.MERGED
        if assessment_type is AssessmentType.TASK:
            return ProfileSource.TASK
        return ProfileSource.DIAGNOSTIC

    def _build_notes(
        self, estimates: dict[str, SkillEstimate], counts: dict[str, int]
    ) -> list[str]:
        """如实说明这份画像有多可信。"""
        notes: list[str] = []

        thin = [code for code, n in counts.items() if n < MIN_ITEMS_PER_SKILL]
        if thin:
            notes.append(
                f"{len(thin)} 项技能的作答不足 {MIN_ITEMS_PER_SKILL} 题，"
                f"能力估计仅供参考，建议增加题量后复测"
            )

        unreliable = [e for e in estimates.values() if e.confidence < CONFIDENCE_RELIABLE]
        if unreliable:
            notes.append(
                f"{len(unreliable)}/{len(estimates)} 项技能的置信度低于 "
                f"{CONFIDENCE_RELIABLE}，界面上以区间而非单一分值呈现"
            )
        return notes

    def _persist_profile(
        self,
        *,
        student_id: str,
        job_id: str | None,
        assessment_id: str | None,
        estimates: dict[str, SkillEstimate],
        source: ProfileSource = ProfileSource.DIAGNOSTIC,
    ) -> SkillProfile:
        profile = SkillProfile(
            id=f"prof_{uuid.uuid4().hex[:16]}",
            student_id=student_id,
            job_id=job_id,
            assessment_id=assessment_id,
            source=source,
            computed_at=utcnow(),
        )
        self._db.add(profile)
        self._db.flush()

        for estimate in estimates.values():
            self._db.add(
                SkillProfileEntry(
                    profile_id=profile.id,
                    skill_code=estimate.skill_code,
                    score=estimate.score,
                    score_low=estimate.score_low,
                    score_high=estimate.score_high,
                    confidence=estimate.confidence,
                    evidence_count=estimate.evidence_count,
                    method=estimate.method,
                )
            )
        self._db.flush()
        return profile

    # ------------------------------------------------------------ 查询
    def latest_profile(
        self, student_id: str, job_id: str | None = None
    ) -> SkillProfile | None:
        filters = [SkillProfile.student_id == student_id]
        if job_id:
            filters.append(SkillProfile.job_id == job_id)
        return (
            self._db.execute(
                select(SkillProfile)
                .options(selectinload(SkillProfile.entries))
                .where(*filters)
                .order_by(SkillProfile.computed_at.desc(), SkillProfile.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

    def item_bank_size(self, job_id: str) -> int:
        return int(
            self._db.execute(
                select(func.count())
                .select_from(AssessmentItem)
                .where(
                    AssessmentItem.job_id == job_id,
                    AssessmentItem.is_active.is_(True),
                )
            ).scalar_one()
        )
