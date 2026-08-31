# 校本培养方案导入指南

本指南的目标是把你们学校的培养方案替换当前北京信息职业技术学院公开局部样例。导入后，课程 Gap 和培养方案优化才可以表述为“基于本校当前材料的分析”。HNJD 2023 方案仍保留为对照样例。

## 请提供的材料

优先提供同一届、同一专业的下列材料：

1. 人工智能技术应用专业人才培养方案（PDF / DOCX，最好含课程体系、学时、课程目标）。
2. 课程标准或课程大纲：特别是数据处理、机器学习、视觉、实训类课程。
3. 实训指导书、评价 Rubric 或课程任务书（可选，但能提高“实践覆盖”判断质量）。
4. 若文件不适合公开，请直接上传到当前对话；不会被写入公开来源或伪造成公开资料。

请不要提供学生名单、成绩、手机号、身份证号等个人信息。若文件包含这些内容，请先脱敏。

## 我会执行的流程

```text
原始校本文件
  → knowledge/manifest.json 登记（来源与授权如实标注）
  → ingest_knowledge.py 切块入库
  → 从原文建立课程与 skill_code 映射
  → seed_curriculum.py --check 严格校验原文引文
  → 导入后重算课程 Gap 与培养方案优化
```

每一条课程与技能映射必须有两类证据：课程本身存在的原文，以及明确涉及该技能的课程目标/内容原文。没有明确文字证据时不建立映射；系统将显示“当前输入未映射”，而不是断言课程没有覆盖。

## 数据文件格式

模板在 [curriculum_plan_TEMPLATE.json](../data/templates/curriculum_plan_TEMPLATE.json)。它不能直接导入，所有 `replace_with_*` 字段都必须替换为真实值。

字段约束：

- `plan.id`：稳定且唯一，例如 `your_school_ai_2026`。
- `source_doc_id`：校本方案进入知识库后的文档 ID。
- `source_chunk_id`：对应已入库的知识块 ID，例如 `doc_your_school_plan_2026#18`。
- `source_quote` / `evidence_quote`：必须是该知识块中的原文；导入器会逐字校验（忽略空白差异）。
- `coverage_strength=1`：正文明确提及；`=2`：课程能力目标明确要求实践。它不是学生学习成效分数。
- `is_partial=false`：仅当已结构化该方案的全部课程且完成核验时才可设置；不确定时保持 `true`。

## 校验与导入命令

以下示例假定校本 JSON 已保存为 `data/seed/curriculum_your_school_2026.json`：

```powershell
# 先确保校本方案原文已入知识库，再校验证据；此命令不会写入课程数据
.venv\Scripts\python.exe scripts\seed_curriculum.py --file data/seed/curriculum_your_school_2026.json --check

# 校验通过后再导入
.venv\Scripts\python.exe scripts\seed_curriculum.py --file data/seed/curriculum_your_school_2026.json
```

导入完成后在教师端选择该方案，或调用：

```text
GET /api/v1/curriculum/{job_id}/gap?plan_id=your_school_ai_2026
GET /api/v1/curriculum/{job_id}/optimization?plan_id=your_school_ai_2026
```

## 验收标准

1. `--check` 通过，且没有未定位的 `source_chunk_id` 或不在原文中的引文。
2. 页面显示正确的 `plan_id`、学校来源和 `is_partial` 状态。
3. 每个推荐可展开回到岗位数据与课程原文证据。
4. 若课程材料仍不完整，页面继续显示局部方案提示；不能在 PPT 中称其为完整校本诊断。
