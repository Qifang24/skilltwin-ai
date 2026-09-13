# 专业建设管理闭环：模板与验收说明

本文是岗位、课程与教师决策的填写和验收参考。模板中的“示例”均为非真实占位，不代表任何企业、岗位、学校或课程，也不表示系统功能已经验证。

## 三阶段链路

1. **岗位需求**：上传 CSV/JSON，完成字段映射、预览、校验、脱敏和重复检查；确认后才写入正式岗位，并进入技能需求分析。
2. **课程对标**：上传 PDF、DOCX、TXT 或结构化 JSON，提取课程结构，使用统一 `skill_code` 建立课程映射。每条映射都要能回到课程原文的 chunk、页码（如有）和连续引文。
3. **优化决策**：将岗位快照、已审核能力图谱和课程覆盖结果合并为缺口与建议。教师可以修改覆盖状态、编辑建议并采纳或忽略；报告只呈现已有证据。

## 岗位导入模板

- CSV：[`job_postings_IMPORT_TEMPLATE.csv`](../data/templates/job_postings_IMPORT_TEMPLATE.csv)
- JSON：[`job_postings_IMPORT_TEMPLATE.json`](../data/templates/job_postings_IMPORT_TEMPLATE.json)
- 字段覆盖：`title`、`company`、`JD`、`skills`、`city`、`date`、`source`、`url`、`salary`、`education`、`experience`。
- `title`、`JD`、`source` 为必填；日期为空时只能提示，格式错误应失败；非空 URL 必须为 HTTP(S)。
- `JD` 应保留职责和任职要求的原文。导入前不得填入手机号、邮箱、微信、QQ 或其他个人联系方式；系统仍应进行二次脱敏。
- CSV 的 `skills` 使用 `|` 分隔；JSON 的 `skills` 使用字符串数组。未知技能只能进入候选审核，不能直接成为规范技能。
- 真实样本与 `DEMO` 样本必须分开统计。没有真实岗位时不得用演示数据替代正式分析。

### 岗位 API 操作顺序

以下路径均相对于 API 前缀（当前部署通常为 `/api/v1`）：

1. `POST /job-imports`（multipart：`file`、`job_id`、`job_name`）创建暂存批次。
2. `PATCH /job-imports/{batch_id}/mapping` 保存字段映射；`GET /job-imports/{batch_id}/preview` 查看前 20 行预览、错误、警告和重复。
3. `POST /job-imports/{batch_id}/confirm` 确认导入；`GET /job-imports/{batch_id}/result` 查看批次结果。
4. `POST /job-market/{job_id}/analyze` 重建技能需求；`GET /job-market/{job_id}/dashboard` 查看排名/趋势；`GET /job-market/{job_id}/postings` 和 `/postings/{posting_id}` 查看岗位证据。

旧版整包接口 `POST /job-market/import` 仍可用于兼容性测试。

## 课程结构化模板

使用 [`curriculum_plan_TEMPLATE.json`](../data/templates/curriculum_plan_TEMPLATE.json)。课程可填写目标、简介、教学内容、知识点、实践内容和学习成果，并为每个字段提供 `chunk_id`、页码和连续原文引文。技能映射应填写三态之一：`covered`、`partial`、`uncovered`，并保留来源、置信度、理由和教师修正信息。

可用 [`curriculum_DEMO_closed_loop.json`](../data/templates/curriculum_DEMO_closed_loop.json) 演示 JSON 结构，但它是合成 `DEMO` fixture，不是真实课程资料。实际课程导入路径为 `POST /curriculum/imports`（multipart：`file`、`source_name`，可选 `source_url`、`license_note`），之后用 `GET /curriculum/imports/{batch_id}/preview` 检查，解析失败可用 `POST /curriculum/imports/{batch_id}/retry`，确认使用 `POST /curriculum/imports/{batch_id}/confirm`。

确认后的读取和修正路径包括：`GET /curriculum/plans`、`GET /curriculum/plans/{plan_id}/courses`、`GET /curriculum/courses/{course_id}/skills`、`POST/PATCH/DELETE /curriculum/courses/{course_id}/skills[/{mapping_id}]`。正式对标使用 `POST /curriculum/analyses`（`job_id`、`plan_id`、`graph_id`），读取使用 `GET /curriculum/analyses?job_id=...&plan_id=...&graph_id=...` 或 `GET /curriculum/analyses/{analysis_id}`，证据下钻使用 `/curriculum/evidence?...&skill_code=...`。

AI 生成的映射只能选择已存在的规范 `skill_code`，且引文必须可以机械核验。教师修改后应立即重算覆盖指标，并记录 `origin`、`teacher_confirmed` 和 `edited_by`。材料不足时显示“当前输入未映射”，不能断言学校没有开设相关内容。

### AI 与安全回退

- 无明确字段标签的课程文档可以交给课程结构化 Agent；每个非空字段都必须提交能在上传原文中逐字找到的连续引文，否则整次 AI 结构化结果作废并保留人工复核草稿。
- 优化建议的需求频率、岗位数、图谱掌握度、覆盖状态、分数、优先级和排序均由确定性算法计算。AI 仅起草结构化的建议类型、标题、内容和理由，不能修改统计事实。
- LLM 调用失败、返回格式错误或技能集合不一致时，系统自动使用规则模板，并在页面、持久化证据和报告中明确标注生成方式；不会把 fallback 冒充 AI 结果。
- `.env.example` 只能保留占位符。需要真实调用时，复制为已被 Git 忽略的 `.env`，在 `.env` 中填写 `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_MODEL` 与 `LLM_API_KEY`，然后重启后端。

## 低样本与证据边界

正式优化需要真实岗位数据。REAL 样本少于 30 条时，所有建议应标记为低样本探索性结果；没有 REAL 样本时应阻止正式优化。课程方案为局部材料时保持 `is_partial=true`。上游岗位、图谱或课程发生变化后，旧运行应保留并标记过期，不覆盖教师历史决定。

## 六个验收场景

1. 用 `POST /job-imports` 上传岗位文件，确认前调用 `/preview`；检查只有暂存批次，并逐行查看字段映射、校验、脱敏和重复原因。
2. 调用 `/confirm` 后再调用 `/result`、`/job-market/{job_id}/analyze` 和 `/dashboard`；重复调用 `/confirm`，确认正式岗位数不增加且岗位证据可下钻。
3. 用 `POST /curriculum/imports` 上传 PDF/DOCX/TXT/JSON，调用 `/preview` 查看解析字段；用无文本 PDF 验证提示文字版或 OCR 版，而不是生成虚假课程。
4. 确认课程方案后调用 `/curriculum/analyses`，从 `/evidence` 查看图谱、岗位和课程依据；通过课程技能 `PATCH/DELETE` 修改后重新读取分析，检查三态覆盖和证据仍在。
5. 仅使用 REAL 岗位调用 `POST /curriculum/optimization-runs` 生成建议，再用 `GET /curriculum/optimizations/{run_id}` 检查持久化结果、确定性优先级和低样本警告。
6. 用 `PATCH /curriculum/optimizations/{run_id}/suggestions/{suggestion_id}` 将建议编辑为 `pending`、`adopted` 或 `ignored`，刷新确认状态；调用 `GET /curriculum/optimizations/{run_id}/report.docx` 下载并重新读取报告证据。

验收记录应写明输入文件、样本类型（REAL/DEMO）、运行时间、失败原因和人工决定。未实际执行的检查不得写成“已通过”。

## 提交边界

只提交模板、脱敏样例、fixtures 和文档。不要提交运行时数据库文件（如 SQLite、上传目录、向量索引）、个人联系方式、访问令牌、API 密钥、`.env` 文件或任何未授权原始招聘/课程材料。`DEMO` fixture 也不得被当作 REAL 数据导入生产分析。
