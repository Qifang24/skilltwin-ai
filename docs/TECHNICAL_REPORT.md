# SkillTwin AI 技术报告（MVP）

## 1. 项目概述

SkillTwin AI 面向人工智能技术应用专业群，以“AI 数据标注工程师”为首个岗位，构建从产业岗位需求到个性化实训与能力更新的闭环。系统不是以聊天为中心：岗位统计、技能 Gap 和学习顺序都由可复算的数据服务产生，LLM 仅用于有证据约束的结构化生成与解释。

## 2. 核心闭环

```text
REAL Job Market Data
  → Skill demand snapshot
  → Approved competency graph
  → Curriculum coverage / gap
  → Structured training task
  → Student assessment and task evidence
  → Student skill profile / gap
  → Replanned learning path
```

所有跨模块关联以 `skill_code` 作为唯一 join key，避免同一技能因中文别名、英文拼写或工具名称变化而被拆为多个维度。

## 3. 系统架构

| 层级 | 主要实现 | 职责 |
|---|---|---|
| 前端 | React + TypeScript + ECharts + Ant Design | 教师/学生工作台、能力图谱、需求排行、技能雷达、Gap 与路径可视化 |
| API | FastAPI + Pydantic + SQLAlchemy | Typed API、错误处理、审计、健康检查 |
| 业务服务 | Job Market / Graph / Curriculum / Task / Assessment / Learning Path / Tutor | 按模块实现智能体职责，避免超级 Prompt |
| LLM Provider | OpenAI-compatible、Spark HTTP、星辰 Workflow、Echo | 可替换模型接入；关键计算不依赖模型 |
| RAG | 文档解析、分块、BGE embedding、Chroma、BM25、RRF | 以 chunk metadata 返回来源、页码/章节（存在时） |
| 数据 | SQLite + Chroma + 文件化 seed/manifest | MVP 本地持久化与可复现初始化 |

## 4. 证据与数据治理

- 公开 JD 样本按来源登记；本轮市场计算使用 30 条 REAL 核心国内 AI 数据标注岗位，旧 2 条 DEMO 样本保留用于开发但自动排除。
- 当前技能命中为 29/30（96.7%）。未匹配岗位保留为未匹配，不能由模型臆测归类。
- 知识库 metadata 保存文档 ID、来源、source type、页码、章节、标准编号（若原文具有）。不制造文献、标准编号或页码。
- 默认课程样例为北京信息职业技术学院 2025 级人工智能技术应用专业（三年制）公开方案的 4 门高相关课程、9 条技能映射，标记为 `is_partial=true`；HNJD 2023 方案保留为对照样例。两者均不是校本结论。
- AI 生成、人工编辑、教师审核、DEMO 数据均保留独立状态，重要界面可展示来源和简短 reasoning summary，而不暴露模型思维链。

## 5. 可部署性与验证

系统提供 Docker Compose：Nginx 同源代理 React 与 FastAPI，SQLite/Chroma/BM25/模型缓存保存在 `skilltwin_data` 持久卷。首次启动会将镜像内版本化 seed 复制到数据卷后初始化，避免数据卷覆盖镜像 seed。健康端点检查 database、LLM 配置、embedding 环境和 vector store。

截至本报告更新：后端自动化测试 274 项通过；前端 lint 与 production build 通过。知识库经页段约束后为 311 个块，15 题检索评测中混合 RAG 的 Recall@5 为 100.0%、MRR 为 0.713。当前开发机未安装 Docker，因此尚未在本机完成 `docker compose up` 的运行态验收；该项应在具备 Docker 的目标环境执行，并按 [DEPLOYMENT.md](DEPLOYMENT.md) 记录结果。

## 6. 当前边界与下一步

1. 导入参赛学校的完整培养方案、课程大纲与校内实训要求，替换公共局部样例。
2. 由专业教师审核 27 项当前 `llm_drafted` 技能表，并留存审核人和版本。
3. 邀请 2–3 名真实教师/学生使用系统，录入任务、预期、实际结果与反馈；未完成前不对外宣称用户验证。
4. 在 Docker 环境完成冷启动、重启、备份恢复和 replay 演示验收。
5. 继续扩展经过来源登记的 JD 与职业标准资料，同时持续展示样本量、时间范围和覆盖边界。
