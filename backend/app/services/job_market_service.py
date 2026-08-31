"""岗位市场分析：原始 JD → 可核验技能命中 → 物化统计 → 趋势视图。

本服务刻意不调用 LLM。技能需求频率、排名与趋势均由确定性规则和 SQL 数据
计算；模型可在后续阶段解释统计结果，但不能决定或改写统计数值。
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.enums import DataFlag, SkillStatus
from app.core.errors import NotFoundError
from app.models.job_market import JobPosting, JobPostingSkill, SkillDemandSnapshot
from app.models.ontology import Job, Skill
from app.schemas.job_market import (
    DemandEvidenceRead,
    JobMarketDashboardRead,
    MarketDataQualityRead,
    SkillDemandRead,
    SkillTrendPointRead,
    SkillTrendSeriesRead,
)


RULE_EXTRACTOR = "rule_v1"


@dataclass
class MarketAnalysisResult:
    dashboard: JobMarketDashboardRead
    extracted_skill_links: int
    snapshots_written: int


class JobMarketService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # ------------------------------------------------------------ 解析
    @staticmethod
    def _terms_for_skill(skill: Skill) -> list[str]:
        """返回可以在原文中精确查找的写法，长写法优先以避免短词抢匹配。"""
        terms = {skill.name_zh, skill.name_en, skill.skill_code, *skill.aliases}
        return sorted(
            {
                term.strip()
                for term in terms
                if term and len(term.strip()) >= 2
            },
            key=len,
            reverse=True,
        )

    @staticmethod
    def _sentence_span(text: str, start: int, end: int) -> str:
        """取含命中词的 JD 原文句，不做摘要或改写。"""
        boundaries = "。！？；\n"
        left = max((text.rfind(char, 0, start) for char in boundaries), default=-1)
        right_candidates = [text.find(char, end) for char in boundaries]
        right = min((pos for pos in right_candidates if pos >= 0), default=len(text))
        span = text[left + 1 : right + 1].strip()
        if len(span) <= 280:
            return span
        # 过长句只截取命中词附近原文，仍保留可定位的原始内容。
        segment_start = max(0, start - 110)
        segment_end = min(len(text), end + 150)
        return text[segment_start:segment_end].strip()

    def _extract_posting(self, posting: JobPosting, skills: list[Skill]) -> int:
        self._db.execute(
            delete(JobPostingSkill).where(JobPostingSkill.posting_id == posting.id)
        )
        created = 0
        for skill in skills:
            for term in self._terms_for_skill(skill):
                match = re.search(re.escape(term), posting.raw_text, flags=re.IGNORECASE)
                if match is None:
                    continue
                self._db.add(
                    JobPostingSkill(
                        posting_id=posting.id,
                        skill_code=skill.skill_code,
                        evidence_span=self._sentence_span(
                            posting.raw_text, match.start(), match.end()
                        ),
                        extractor=RULE_EXTRACTOR,
                        extractor_version="2026-08",
                        confidence=1.0,
                    )
                )
                created += 1
                break
        return created

    # ------------------------------------------------------------ 统计
    @staticmethod
    def _month_window(value: datetime) -> tuple[datetime, datetime]:
        start = datetime(value.year, value.month, 1, tzinfo=timezone.utc)
        if value.month == 12:
            end = datetime(value.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(value.year, value.month + 1, 1, tzinfo=timezone.utc)
        return start, end

    def _write_window(
        self,
        *,
        job_id: str,
        postings: list[JobPosting],
        window_start: datetime | None,
        window_end: datetime | None,
        now: datetime,
    ) -> int:
        if not postings:
            return 0
        total = len(postings)
        real_count = sum(p.data_flag is DataFlag.REAL for p in postings)
        demo_count = total - real_count
        mentions: dict[str, set[str]] = defaultdict(set)
        for posting in postings:
            for link in posting.skills:
                mentions[link.skill_code].add(posting.id)

        count = 0
        for skill_code, posting_ids in mentions.items():
            self._db.add(
                SkillDemandSnapshot(
                    job_id=job_id,
                    skill_code=skill_code,
                    window_start=window_start,
                    window_end=window_end,
                    posting_count=len(posting_ids),
                    total_postings=total,
                    frequency=len(posting_ids) / total,
                    real_posting_count=real_count,
                    demo_posting_count=demo_count,
                    computed_at=now,
                )
            )
            count += 1
        return count

    def analyze(self, job_id: str) -> MarketAnalysisResult:
        job = self._db.get(Job, job_id)
        if job is None:
            raise NotFoundError(f"未找到岗位：{job_id}", detail={"job_id": job_id})

        postings = list(
            self._db.execute(
                select(JobPosting)
                .options(selectinload(JobPosting.skills))
                .where(JobPosting.job_id == job_id)
                .order_by(JobPosting.id)
            ).scalars()
        )
        skills = list(
            self._db.execute(
                select(Skill)
                .where(Skill.status == SkillStatus.ACTIVE)
                .order_by(Skill.skill_code)
            ).scalars()
        )

        extracted = 0
        for posting in postings:
            extracted += self._extract_posting(posting, skills)
        self._db.flush()
        # ``postings`` was loaded with ``selectinload`` before new link rows
        # were inserted.  Expire it before rebuilding the aggregate so the
        # relationship is read from the database instead of the stale empty
        # collection held in SQLAlchemy's identity map.
        self._db.expire_all()

        refreshed = list(
            self._db.execute(
                select(JobPosting)
                .options(selectinload(JobPosting.skills))
                .where(JobPosting.job_id == job_id)
                .order_by(JobPosting.id)
            ).scalars()
        )
        # 当存在真实 JD 时，DEMO 记录只能用于本地演示与管线回归，绝不能进入
        # 对外的需求频率、排名和趋势。只有完全没有真实样本的开发环境才退回使用
        # DEMO，以便页面仍可被开发者检查。
        real_postings = [
            posting for posting in refreshed if posting.data_flag is DataFlag.REAL
        ]
        analysis_postings = real_postings or refreshed
        self._db.execute(
            delete(SkillDemandSnapshot).where(SkillDemandSnapshot.job_id == job_id)
        )
        now = datetime.now(timezone.utc)
        written = self._write_window(
            job_id=job_id,
            postings=analysis_postings,
            window_start=None,
            window_end=None,
            now=now,
        )

        by_window: dict[tuple[datetime, datetime], list[JobPosting]] = defaultdict(list)
        for posting in analysis_postings:
            if posting.posted_at is not None:
                by_window[self._month_window(posting.posted_at)].append(posting)
        for (start, end), window_postings in sorted(by_window.items()):
            written += self._write_window(
                job_id=job_id,
                postings=window_postings,
                window_start=start,
                window_end=end,
                now=now,
            )
        self._db.flush()

        dashboard = self.dashboard(job_id)
        return MarketAnalysisResult(
            dashboard=dashboard,
            extracted_skill_links=extracted,
            snapshots_written=written,
        )

    # ------------------------------------------------------------ 读取
    def _quality(self, job_id: str) -> MarketDataQualityRead:
        postings = list(
            self._db.execute(
                select(JobPosting)
                .options(selectinload(JobPosting.skills))
                .where(JobPosting.job_id == job_id)
            ).scalars()
        )
        total = len(postings)
        real = sum(p.data_flag is DataFlag.REAL for p in postings)
        demo = total - real
        # 数据质量中与“统计样本”相关的指标必须使用和排名相同的口径：有真实
        # JD 时只审计 REAL；仅在开发库没有真实样本时才回退到 DEMO。
        analysis_postings = (
            [posting for posting in postings if posting.data_flag is DataFlag.REAL]
            if real
            else postings
        )
        analysis_total = len(analysis_postings)
        with_skills = sum(bool(posting.skills) for posting in analysis_postings)
        missing_date = sum(posting.posted_at is None for posting in analysis_postings)
        fingerprints = Counter(
            re.sub(r"\s+", "", posting.raw_text).casefold()
            for posting in analysis_postings
        )
        duplicate_count = sum(count - 1 for count in fingerprints.values() if count > 1)
        dated = [posting.posted_at for posting in analysis_postings if posting.posted_at]

        warnings: list[str] = []
        if total == 0:
            warnings.append("当前没有已导入岗位样本，请先导入合法公开 JD 后再分析。")
        if demo:
            warnings.append(
                (
                    f"当前岗位库含 {demo} 条 DEMO 数据；"
                    + (
                        "因已存在 REAL 样本，DEMO 已被排除在需求排名与趋势统计之外。"
                        if real
                        else "当前没有 REAL 样本，图表仅用于开发管线演示，不能作为对外行业结论。"
                    )
                )
            )
        if real and real < 30:
            warnings.append(
                f"真实样本仅 {real} 条，低于建议的 30 条；频率用于教学探索，不宜作稳定趋势判断。"
            )
        if missing_date:
            warnings.append(
                f"{missing_date} 条 JD 缺少发布时间，已计入技能排名但不计入月度趋势。"
            )
        if duplicate_count:
            warnings.append(
                f"检测到 {duplicate_count} 条重复岗位正文，重复会抬高频率，建议在导入前去重。"
            )
        if analysis_total and with_skills < analysis_total:
            warnings.append(
                f"{analysis_total - with_skills} 条统计样本未匹配到规范技能，需补充技能别名或人工复核原文。"
            )

        return MarketDataQualityRead(
            total_postings=total,
            real_postings=real,
            demo_postings=demo,
            postings_with_skills=with_skills,
            extraction_coverage=with_skills / analysis_total if analysis_total else 0.0,
            missing_posted_at=missing_date,
            duplicate_raw_text_count=duplicate_count,
            latest_posted_at=max(dated) if dated else None,
            warnings=warnings,
        )

    def _evidence(
        self, job_id: str, skill_code: str, *, real_only: bool
    ) -> list[DemandEvidenceRead]:
        statement = (
            select(JobPostingSkill, JobPosting)
            .join(JobPosting, JobPosting.id == JobPostingSkill.posting_id)
            .where(
                JobPosting.job_id == job_id,
                JobPostingSkill.skill_code == skill_code,
            )
            .order_by(JobPosting.posted_at.desc(), JobPosting.id)
            .limit(5)
        )
        if real_only:
            statement = statement.where(JobPosting.data_flag == DataFlag.REAL)
        rows = self._db.execute(statement).all()
        return [
            DemandEvidenceRead(
                posting_id=posting.id,
                title=posting.title,
                company_type=posting.company_type,
                city=posting.city,
                posted_at=posting.posted_at,
                source_name=posting.source_name,
                source_url=posting.source_url,
                data_flag=posting.data_flag,
                evidence_span=link.evidence_span,
            )
            for link, posting in rows
        ]

    def dashboard(
        self,
        job_id: str,
        *,
        top_n: int = 10,
        trend_skill_codes: list[str] | None = None,
    ) -> JobMarketDashboardRead:
        job = self._db.get(Job, job_id)
        if job is None:
            raise NotFoundError(f"未找到岗位：{job_id}", detail={"job_id": job_id})

        quality = self._quality(job_id)
        # 与 analyze() 的选择规则保持一致，避免旧快照或意外 DEMO 证据混入
        # 已有真实样本的教师端统计。
        real_only = quality.real_postings > 0
        all_time = list(
            self._db.execute(
                select(SkillDemandSnapshot)
                .where(
                    SkillDemandSnapshot.job_id == job_id,
                    SkillDemandSnapshot.window_start.is_(None),
                    SkillDemandSnapshot.window_end.is_(None),
                )
                .order_by(
                    SkillDemandSnapshot.frequency.desc(),
                    SkillDemandSnapshot.posting_count.desc(),
                    SkillDemandSnapshot.skill_code,
                )
                .limit(top_n)
            ).scalars()
        )
        skill_codes = [snapshot.skill_code for snapshot in all_time]
        skills = {
            skill.skill_code: skill
            for skill in self._db.execute(
                select(Skill).where(Skill.skill_code.in_(skill_codes))
            ).scalars()
        } if skill_codes else {}
        ranking = [
            SkillDemandRead(
                skill_code=snapshot.skill_code,
                skill_name=skills.get(snapshot.skill_code).name_zh
                if snapshot.skill_code in skills
                else None,
                category=skills.get(snapshot.skill_code).category.value
                if snapshot.skill_code in skills
                else None,
                posting_count=snapshot.posting_count,
                total_postings=snapshot.total_postings,
                frequency=snapshot.frequency,
                real_posting_count=snapshot.real_posting_count,
                demo_posting_count=snapshot.demo_posting_count,
                is_demo_contaminated=snapshot.is_demo_contaminated,
                evidence=self._evidence(
                    job_id, snapshot.skill_code, real_only=real_only
                ),
            )
            for snapshot in all_time
        ]

        requested = trend_skill_codes or skill_codes[:5]
        trends: list[SkillTrendSeriesRead] = []
        for code in requested:
            snapshots = list(
                self._db.execute(
                    select(SkillDemandSnapshot)
                    .where(
                        SkillDemandSnapshot.job_id == job_id,
                        SkillDemandSnapshot.skill_code == code,
                        SkillDemandSnapshot.window_start.is_not(None),
                    )
                    .order_by(SkillDemandSnapshot.window_start)
                ).scalars()
            )
            if not snapshots:
                continue
            skill = skills.get(code) or self._db.get(Skill, code)
            trends.append(
                SkillTrendSeriesRead(
                    skill_code=code,
                    skill_name=skill.name_zh if skill else None,
                    points=[
                        SkillTrendPointRead(
                            window_start=snapshot.window_start,
                            window_end=snapshot.window_end,
                            posting_count=snapshot.posting_count,
                            total_postings=snapshot.total_postings,
                            frequency=snapshot.frequency,
                            real_posting_count=snapshot.real_posting_count,
                            demo_posting_count=snapshot.demo_posting_count,
                        )
                        for snapshot in snapshots
                        if snapshot.window_start is not None and snapshot.window_end is not None
                    ],
                )
            )

        computed_at = self._db.execute(
            select(func.max(SkillDemandSnapshot.computed_at)).where(
                SkillDemandSnapshot.job_id == job_id
            )
        ).scalar_one()
        return JobMarketDashboardRead(
            job_id=job.id,
            job_name=job.name,
            data_quality=quality,
            ranking=ranking,
            trends=trends,
            computed_at=computed_at,
        )
