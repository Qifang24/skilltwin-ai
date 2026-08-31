# 规范技能表教师审核指南

这一步审核的是系统的 **27 项规范技能与 35 条原文证据**，不是审核 AI 生成的措辞是否“看起来合理”。审核完成前，所有条目保持 `llm_drafted`，不得在比赛材料中称作“已由教师审核”。

## 审核包的生成

在项目根目录执行：

```powershell
# 只检查技能、来源和证据是否齐全
.venv\Scripts\python.exe scripts\export_skill_review_packet.py --check

# 导出供 Excel / WPS 填写的审核包（UTF-8 with BOM）
.venv\Scripts\python.exe scripts\export_skill_review_packet.py
```

默认输出为 `data/review/skill_review_packet.csv`。该目录被 Git 忽略，避免把审核人姓名、意见或日期提交到代码库。若需要交付审核凭据，请经审核人同意后以受控方式保存。

每一行代表“一个技能的一条原文证据”。同一 `skill_code` 可能出现多行，必须对该技能的所有证据行完成审核。`source_chunk_id` 和 `page` 可用于在系统中回查原文。

## 教师填写规则

请由具备人工智能技术应用、数据标注实训或课程建设经验的教师填写如下字段：

| 字段 | 填写要求 |
| --- | --- |
| `review_decision` | 仅填 `approve`、`revise` 或 `reject`。同一技能的多条证据必须使用同一结论。 |
| `reviewed_name_zh` | `revise` 时必填；`approve` 时可留空，表示认可提议名称。 |
| `reviewed_description` | `revise` 时填写可测评、可教学的修订说明。 |
| `review_notes` | `revise` / `reject` 时必填，说明原因，例如“标准原文只支持工具认知，不足以支持独立操作”。 |
| `reviewer_alias` | 审核人可识别的姓名、工号后四位或经同意的匿名代号；不填写学生个人信息。 |
| `reviewed_at` | 实际审核日期，格式 `YYYY-MM-DD`。 |

审核时至少判断：

1. `skill_code` 是否能作为全系统稳定 join key；
2. 中文名、类别、描述是否与岗位入门层级相符且可测评；
3. 原文引句是否确实支撑该技能，而不是只出现相似词；
4. 别名是否会与其他技能混淆；
5. 该技能是否适用于“AI 数据标注工程师”目标岗位，而非高等级晋升岗位能力。

## 回填到系统

1. 保存填写完成的 CSV；保留原始审核包，不覆盖。
2. 对 `revise` 项，人工修改 `data/seed/skills_ai_data_annotator.json` 中相应的名称、描述、别名或来源；不得删除原始证据来掩盖问题。
3. 对 `reject` 项，先确认它是否已被下游图谱、测评或课程映射引用；有引用时应先替换引用，再按废弃流程处理。
4. 仅当同一技能全部证据行均为 `approve`，且填写了真实审核人和实际日期时，才可把该技能的 `provenance` 改为 `human_reviewed`。
5. 运行下面两项校验，再重新导入技能表：

```powershell
.venv\Scripts\python.exe scripts\seed_skills.py --check
.venv\Scripts\python.exe scripts\seed_skills.py --file data/seed/skills_ai_data_annotator.json
```

当前导入器会按 seed 原样更新数据库，因此第 4 步必须在真实审核完成后执行，不能为演示提前修改。

## 比赛中的合规表述

审核前：**“技能表由国家职业技能标准原文证据抽取生成，待领域教师审核。”**

审核后：**“技能表经教师审核；系统保留原文证据、审核日期和修订记录。”** 前提是确实保存了对应审核包，且能够按需出示。
