"""ORM 模型注册表。

导入本包即完成全部模型注册，create_all / drop_all 依赖于此。
后续 Phase 新增的表（job_posting / course / training_task / student ...）
在此追加导出即可。
"""

from app.models.audit import Citation, LLMRun
from app.models.competency import CompetencyEdge, CompetencyGraph, CompetencyNode
from app.models.curriculum import (
    CourseSkillCoverage,
    CurriculumAnalysis,
    CurriculumCourse,
    CurriculumDraftCourse,
    CurriculumImportBatch,
    CurriculumPlan,
    OptimizationRun,
    OptimizationSuggestion,
    SkillCoverage,
    SuggestionEvidence,
)
from app.models.job_market import (
    JobImportBatch,
    JobImportRow,
    JobPosting,
    JobPostingSkill,
    JobSkillCandidate,
    SkillDemandSnapshot,
)
from app.models.learning import (
    LearningPathActivity,
    LearningPath,
    LearningPathItem,
    LearningPathPhase,
)
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.models.ontology import Job, Skill
from app.models.student import (
    Assessment,
    AssessmentItem,
    AssessmentItemSkill,
    AssessmentResponse,
    SkillProfile,
    SkillProfileEntry,
    Student,
)
from app.models.training import TrainingTask, TrainingTaskSkill
from app.models.tutor import TutorConversation, TutorMessage
from app.models.user_testing import UserTestSession, UserTestTaskRecord

__all__ = [
    "Assessment",
    "AssessmentItem",
    "AssessmentItemSkill",
    "AssessmentResponse",
    "Citation",
    "CompetencyEdge",
    "CompetencyGraph",
    "CompetencyNode",
    "CourseSkillCoverage",
    "CurriculumAnalysis",
    "CurriculumCourse",
    "CurriculumDraftCourse",
    "CurriculumImportBatch",
    "CurriculumPlan",
    "Job",
    "JobPosting",
    "JobPostingSkill",
    "JobImportBatch",
    "JobImportRow",
    "JobSkillCandidate",
    "KnowledgeChunk",
    "KnowledgeDoc",
    "LearningPath",
    "LearningPathActivity",
    "LearningPathItem",
    "LearningPathPhase",
    "LLMRun",
    "Skill",
    "SkillCoverage",
    "SkillDemandSnapshot",
    "OptimizationRun",
    "OptimizationSuggestion",
    "SuggestionEvidence",
    "SkillProfile",
    "SkillProfileEntry",
    "Student",
    "TrainingTask",
    "TrainingTaskSkill",
    "TutorConversation",
    "TutorMessage",
    "UserTestSession",
    "UserTestTaskRecord",
]
