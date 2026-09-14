# SkillTwin AI

> 职业教育岗位能力与个性化实训智能体
> **让岗位定义学习，让能力驱动成长**

面向「高水平专业群建设的教学实训与岗位技能智能体」场景，构建
`产业 → 岗位 → 能力 → 课程 → 实训 → 学生 → 个性化学习` 的完整闭环。

当前进度：**Phase 18（讯飞星火 / 星辰 Workflow 平台适配）已完成；真实用户样本待录入**。

规范技能表当前有 27 项、35 条原文证据，均为待教师确认的 `llm_drafted` 状态。可按 [教师审核指南](docs/SKILL_REVIEW_GUIDE.md) 导出审核包；未获得真实审核前，系统不会把它们表述为人工审核结论。

真实用户测试采用匿名会话与逐任务记录；现场可按 [用户测试执行清单](docs/USER_TESTING_RUNBOOK.md) 操作。完成会话少于 2 份时，系统会明确提示其不能作为结论性验证。

- 教师侧：`生成图谱 → 审核确认 → 由能力单元生成实训任务 → 发布给学生`
- 学生侧：`选定目标岗位 → 能力诊断 → 能力画像（带置信区间）→ 能力差距`
- AI Tutor：`学生画像 + 当前实训任务 + 最近 3 轮对话 + RAG 证据 → 情境化辅导与可追溯依据`

---

## 设计铁律

这三条贯穿全部代码，是本系统区别于「套壳聊天机器人」的地方：

1. **LLM 只做「生成与解释」，不做「统计与排序」。**
   技能频次、Gap 数值、学习路径顺序，全部由 SQL / numpy 确定性计算。
   模型只负责把数字写成人话并给出建议。

2. **`skill_code` 是全系统唯一的 join key。**
   岗位需求、课程覆盖、实训任务、测评题、学生画像，都归一到规范技能表。
   没有这一层，`Label Studio` / `LabelStudio` / `标注工具Label Studio`
   会变成三个维度，让 Gap Analysis **静默算错**。

3. **能力图谱是持久化本体，不是每次现场生成的临时结构。**
   LLM 产出 `draft` → 教师审核 → `approved` 才可被下游引用。
   只有节点 ID 稳定，两次 Skill Gap 才具备可比性。

配套的数据原则：严禁伪造文献、标准编号与页码；无依据时明确输出
「当前知识库暂无足够依据」；演示数据一律带 `DEMO` 标记。

---

## 环境要求

| 项 | 版本 | 说明 |
|---|---|---|
| Python | 3.10+ | 本项目在 3.10.11 上开发验证 |
| Node.js | 20+ | 本项目在 24.14.0 上开发验证 |
| GPU | 可选 | 有 CUDA 则本地 embedding 走 GPU，无则自动回落 CPU |

---

## 快速开始

### 1. 后端

```bash
# 在项目根目录
python -m venv .venv --system-site-packages
.venv/Scripts/python.exe -m pip install -r backend/requirements-local.txt

# 配置环境变量
cp .env.example .env        # 然后编辑 .env 填入你的 LLM_API_KEY

# 建表
.venv/Scripts/python.exe scripts/reset_db.py

# 启动（默认 127.0.0.1:8000）
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

> **`--system-site-packages` 是刻意选择**：复用机器上已有的
> `torch` / `chromadb` / `sentence-transformers`，避免重复下载约 2.4GB。
> 同时 venv 内钉死的 `fastapi==0.115.6` + `starlette==0.41.3`
> 会遮蔽全局可能存在的不兼容版本。

API 文档：<http://127.0.0.1:8000/docs>

### 2. 前端

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

前端通过 Vite 代理访问 `/api` → `127.0.0.1:8000`，开发期无需处理 CORS。

### 3. 测试

```bash
cd backend
../.venv/Scripts/python.exe -m pytest
```

测试**不联网**：`tests/conftest.py` 会用假 Key 与不可路由的 base_url
遮蔽 `.env`，避免意外调用真实接口烧 token。

```bash
cd frontend
npm run build                                # tsc -b && vite build
```

真实模型链路冒烟（会消耗少量 token）：

```bash
.venv/Scripts/python.exe scripts/smoke_llm.py
```

### 4. Docker 部署（Phase 17）

项目提供同源 Nginx + FastAPI 的 Docker Compose 部署，运行数据持久化在 Docker named volume，
不会把 API Key 编译进前端。详细步骤、备份和云端约束见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。
若要将 React 前端与 FastAPI 后端一起部署到 Vercel，请按 [Vercel 完整部署指南](docs/VERCEL.md) 配置托管 Postgres、环境变量与初始数据。

```powershell
Copy-Item .env.example .env
# 编辑 .env 后填入真实 LLM 配置
docker compose up --build -d
```

启动后访问 <http://localhost:8080>。首次 RAG 建索引会下载本地 embedding 模型；不具备 Docker
或云平台权限时，本仓库不能宣称已经公网发布。

### 5. 讯飞星火 / 星辰平台适配（Phase 18）

支持两种独立、可审计的讯飞接入方式：星火 HTTP 模型 Provider（使用 HTTP APIPassword）和
星辰 Agent Workflow Provider（使用已发布 `flow_id` 及 `API_KEY:API_SECRET`）。完整配置、
工作流参数约定、安全边界和官方文档链接见 [docs/XFYUN_XINGCHEN.md](docs/XFYUN_XINGCHEN.md)。

两种 Provider 均保留本地 RAG、引用核验、`llm_run` 审计及 `DEMO_MODE=replay`；平台密钥不能
写入前端、代码、种子数据或测试文件。

依次验证真实调用 → 缓存命中 → 断网回放三条链路。

---

## 模型调用模式（DEMO_MODE）

比赛演示只有一次机会，网络和限流都不可控，因此调用层内建了录制回放：

| 模式 | 行为 | 用途 |
|---|---|---|
| `live` | 总是真实调用，仍然落盘 | 默认 |
| `record` | 优先命中缓存，未命中才真调 | **开发期推荐**，不重复烧 token |
| `replay` | 只读缓存，未命中直接报错 | **演示当天**，断网也能跑 |

回放的是**此前真实产生**的结果，不是编造的假数据，且前端会明确提示
「本次结果来自缓存回放」。`replay` 模式在**没有 API Key 的机器上也能运行** ——
备用笔记本演示时这条路径必须成立。

每次调用都会写入 `llm_run` 表，可通过 `GET /api/v1/llm-runs/{id}`
查到输入摘要、原始输出、耗时、token 与引用记录。

---

## 知识库

来源全部为**可核验的公开文件**，清单见 [knowledge/manifest.json](knowledge/manifest.json)。

| 文档 | 来源 | 块数 |
|---|---|---|
| 《人工智能训练师国家职业技能标准（2021年版）》 | 人社部、工信部制定，职业编码 4-04-05-05 | 22 |
| 《高等职业学校人工智能技术应用专业实训教学条件建设标准》 | 教育部（moe.gov.cn 官方发布） | 48 |
| 《数据标注产业发展研究报告（2025年）》 | 中国信通院（caict.ac.cn 官方发布） | 93 |
| 河南机电职业学院《人工智能技术应用专业人才培养方案（2023级）》 | 院校官网公开发布，专业代码 510209 | 80 |
| 北京信息职业技术学院《人工智能学院人才培养方案》（2025年6月修订） | 院校信息公开栏目；仅摄取人工智能技术应用专业三年制 PDF 物理页 270–307 | 68 |

共 311 个知识块，其中 **91% 可精确定位到印刷页码**。

```bash
.venv/Scripts/python.exe scripts/ingest_knowledge.py --dry-run  # 预览切块
.venv/Scripts/python.exe scripts/ingest_knowledge.py            # 入库
```

### 检索

```bash
.venv/Scripts/python.exe scripts/build_index.py        # 建向量 + BM25 索引
.venv/Scripts/python.exe scripts/eval_retrieval.py --compare   # 评测
```

双通路混合：**dense**（本地 BGE 向量）+ **BM25**（jieba 分词），经 RRF 融合。

RRF 只用**排名**不用分数，因此免疫两路分数量纲不同的问题（向量相似度 0~1，
BM25 无上界且随语料变化）——无需调权重，换语料也不失效。

### 检索效果（15 题评测集，311 块语料）

| 策略 | Recall@5 | MRR |
|---|---|---|
| 仅向量 | 80.0% | 0.547 |
| 仅 BM25 | 93.3% | **0.758** |
| **混合 + RRF** | **100.0%** | 0.713 |

**诚实的结论：混合检索的价值在召回率，不在排序精度。** BM25 的 MRR 更高
0.045；之所以仍用混合，是因为它对每一题都能召回相关内容，
而单路做不到——RAG 场景下模型会看到全部 top-N，「有没有找到」比「排第几」更重要。

评测集本身也经程序核实：`--verify` 会检查每题的关键词确实存在于期望文档中。
没有评测集的 RAG 是不可信的——改了分块大小、换了模型、调了参数，
无法说清究竟变好还是变坏。

### 关于页码的一个要害细节

引用必须给出**印刷页码**（读者翻开原文能对上的那个数字），而非 PDF 物理页序。
以国标为例，PDF 第 10 页页脚印的是「6」。更麻烦的是 pypdf 会把两位数页码
逆序抽出（"10" → "0 1"）—— 若不处理，引用会把读者指向**错误的页**，
且表面上完全看不出问题。

处理方式不是猜数字顺序，而是用「页码随页序等差递增」这一约束自校验：
先从无歧义的单位数页求出偏移量，再用它裁决多位数候选。
**读不到页码的页面一律留空**，引用退化为只标章节 —— 绝不用偏移量凭空推算。

manifest 里 `standard_id` 为 `null` 的文档，入库后该字段就是空，引用时直接省略。
宁可缺失，不可编造。

---

## 岗位能力图谱（Module 2）

全系统的数据中枢。生命周期：

```
LLM + RAG  →  draft  →  教师审核修改  →  approved（节点 ID 冻结）
                                            │
                        ┌───────────────────┼───────────────────┐
                     课程映射            实训任务          学生能力向量
```

```bash
POST /api/v1/graphs/generate            # {"job_id": "ai_data_annotator"}
GET  /api/v1/graphs/{id}                # 可直接渲染的嵌套树
GET  /api/v1/graphs/{id}/nodes/{nid}    # 节点依据下钻
POST /api/v1/graphs/{id}/approve        # {"approved_by": "张老师"}
GET  /api/v1/graphs/{id}/target-vector  # 目标能力向量
```

### 教师审核界面

```bash
cd backend && ../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
cd frontend && npm run dev
```

打开 <http://localhost:5173/teacher>：

| 页面 | 能做什么 |
|---|---|
| 教师工作台 | 查看图谱列表、一键生成新草案 |
| 图谱审核页 | 左侧树图 + 右侧节点详情，点节点看**依据原文与页码**，可改名/改掌握程度/删节点，确认后审核通过 |

界面上的三处刻意设计：

- **节点标 `AI 生成` / `人工添加` / `经教师修订`**，树图里改过的节点带 `✎`
  —— 演示时能说清哪些是模型产出、哪些经过人工把关
- **依据区展示来源、章节、页码与原文引文**，缺依据的节点会明确提示
- **已审核图谱整页转为只读**，并说明原因（下游引用了这些编码）

### 三条把关

| 关卡 | 作用 |
|---|---|
| **节点 ID 由服务端分配** | 模型给的 ID 不稳定，而 ID 是下游全部外键的锚点 |
| **技能点必须能 join 到技能表** | 解析不了的节点直接丢弃——没有 `skill_code` 的技能点在下游无法关联，留着只制造「看起来很完整」的假象 |
| **只有 approved 可被引用** | 同一岗位只保留一份 approved，旧版自动归档；没有技能点的图谱不允许通过审核 |

模型引用了不存在的依据编号会被忽略并记入 `warnings`，不会被当作「它有依据」。

### 层级对齐职业标准

```
职业功能    →  competency        能力
工作内容    →  competency_unit   能力单元
技能要求    →  skill_point       技能点
相关知识要求 →  knowledge_point   知识点
```

不是巧合——职业标准本就按「能力如何分解」组织，顺着它走，图谱才有据可依。
实测生成的顶层能力（数据采集与处理 / 数据标注 / 智能系统运维）
正是国标五级/初级工的三个职业功能。

### Target Skill Vector

`GET /graphs/{id}/target-vector` 把图谱折成 `{skill_code: mastery_level}`，
同一技能取最高要求。**这是教师侧与学生侧的连接点**：同一份 approved 图谱，
既是课程 Gap 分析的对标基准，也是学生能力测评的目标基线。

---

## 实训任务（Module 3）

从**已审核**图谱的能力单元一键生成，全部结构化而非一段 Markdown。

```
POST /api/v1/training-tasks/generate    # {"node_id": "...unit3", "difficulty": "beginner"}
GET  /api/v1/training-tasks/{id}
POST /api/v1/training-tasks/{id}/publish
```

界面：教师工作台 → 打开已审核图谱 → 点能力单元节点 → 「由此能力生成实训任务」。

### 为什么结构化

`objectives` / `steps` / `rubric` / `common_mistakes` 全部是结构化字段，不是整篇文本：

- 前端能按区块渲染，教师上课可单独看步骤或量规
- **`rubric` 会被 Phase 8 的测评直接读取**，把得分按权重回写到学生能力画像
- 教师可以只改其中一步，而不必重写整篇

### 两条把关

**只能从 approved 图谱派生。** 草案图谱的节点编码仍会变动，据此生成的任务
会在图谱改版后留下悬空引用。

**归因跟随学习目标，不是能力单元的全量技能。** 能力单元「原始数据清洗与标注」
涵盖文本/视觉/规范三项，但一个只练图像标注的任务若按单元全量关联，
学生做完会连带拿到文本标注的加分 —— 那在 Phase 8 回写能力画像时是实打实的算错。
目标未标注技能编码时会退回单元技能，并明确提示「归因偏粗」。

评分量规权重合计不为 100 时会警告但不拒绝 —— 教师有理由用别的计分方式，
不该由系统一刀切。

---

## 学生能力测评（Module 4）

```
POST /api/v1/students                              # 只存化名
POST /api/v1/students/{id}/assessments             # 组卷
POST /api/v1/assessments/{id}/submit               # 交卷并生成画像
GET  /api/v1/students/{id}/skill-profile           # 能力画像
GET  /api/v1/students/{id}/skill-gap               # 对标图谱的能力差距
DELETE /api/v1/students/{id}                       # 合规：彻底删除
```

界面：<http://localhost:5173/student>

### 能力值不撒谎

**判分与能力估计全程没有 LLM 参与**，用 Wilson 得分区间做小样本比例估计：

| 作答 | 点估计 | 95% 区间 | 置信度 | 可信? |
|---|---|---|---|---|
| 未测评 | 50.0 | [0, 100] | 0.00 | 否 |
| 3/3 全对 | **71.9** | [43.9, 100] | 0.44 | 否 |
| 18/20 | 83.6 | [69.9, 97.2] | 0.73 | 是 |

**三题全对给 71.9 分而非 100** —— 样本太小，撑不起「能力 100」这个结论。
常用的 Wald 区间在此会给出 [100%, 100%]，Wilson 不会。

**「未测评」是 [0,100] 完全不确定，不是 0 分。** 把没测过显示成 0 分，
会让学生以为自己这项很差，是实实在在的误导；学习路径也会因此把
「没测过」当成「很差」来排，浪费学生时间。

### 统计效力提示说在做题之前

```
⚠ 本卷 16 题覆盖 14 项技能，平均每项约 1.1 题。
  能力估计需要每项至少 3 题才可信，本次结果将主要用于初步定位薄弱方向，
  不宜作为精确评价。如需可信结论，建议出到 42 题以上。
```

等交完卷才说「14 项全部不可信」，学生已经白做了一遍。

### 图表怎么表达不确定性

- **雷达图**只画点估计，证据不足的维度轴标签加 `⚠`
- **能力区间图**画 95% 区间色带：**带越宽 = 越不确定**，
  证据不足的带画成灰色。「3 题得 71.9」与「20 题得 83.6」
  在雷达图上看着差不多，区间图上一眼就能看出差别

```bash
.venv/Scripts/python.exe scripts/generate_items.py --per-skill 4   # 生成题库
```

题库生成会主动报告哪些技能题量不足 3 题、其估计不可信。

---

## 个性化学习路径（Phase 9A–9D）

后端最小纵向闭环已经接通：

```bash
POST /api/v1/students/{id}/learning-paths/generate
GET  /api/v1/students/{id}/learning-paths/latest
```

生成顺序固定为：

```text
目标岗位对应的最新画像 → approved 图谱目标向量 → Skill Gap
→ 前置依赖拓扑分层 → 同层按 Gap 降序 → Agent 撰写阶段文案
→ 挂接已发布实训任务 → 持久化路径
```

三条可信度约束：

- **未测评不等于零分**：`evidence_count=0` 的技能不进入学习阶段，只提示补测。
- **低置信度不隐藏**：已有作答但证据不足时可以生成初步路径，同时写入明确警告。
- **LLM 不决定顺序**：模型只能撰写标题、说明与行动建议；阶段顺序由图谱前置关系和 Gap 确定性计算。

示例：

```json
{
  "job_id": "ai_data_annotator",
  "max_phases": 4
}
```

### 复测后的完整画像快照（Phase 9B）

局部复测不会再让未覆盖技能从最新画像中消失：

```text
上一份同岗位完整画像
       +
本次实际测到的技能（覆盖旧值）
       ↓
新一份完整画像快照（source=merged）
```

- 本次测到的技能采用新估计，返回在 `updated_skill_codes`。
- 未测到的技能原样继承，返回在 `inherited_skill_codes`。
- 继承项不增加 `evidence_count`、不提高 `confidence`，避免伪造新证据。
- 只继承同一 `student_id + job_id` 的画像，切换岗位时能力向量完全隔离。
- 不对两次分数做简单平均：现有快照不足以恢复联合统计分布，硬平均会制造假精度。

### 学生端学习路径 Timeline（Phase 9C）

学生端 `/student` 已接入真实学习路径 API：

- 学生选择写入 URL 查询参数，诊断、画像、Gap 和路径可直接回到同一学生上下文。
- 没有路径时显示可解释空态；有可测 Gap 后可请求生成或刷新路径。
- Timeline 展示阶段顺序、目标技能、学习行动、知识资源、已发布实训任务和复测入口。
- Agent 文案明确标记“AI 生成”，并展示生成依据、告警、置信度和可用来源。
- 实训链接进入学生视图，不显示教师发布操作；复测会回到当前学生的完整岗位测试。

### 自适应学习闭环（Phase 9D）

学习项状态、进度和复测已形成真实持久化闭环：

```bash
PATCH /api/v1/students/{student_id}/learning-path-items/{item_id}
POST  /api/v1/students/{student_id}/learning-path-items/{item_id}/retest
```

- 知识学习、行动建议和实训任务支持完成、重新打开与跳过，路径和阶段进度由服务端重算。
- 每次状态变化写入 `learning_path_activity`，保留前后状态、关联资源、时间与说明。
- 点击“完成实训”只记录学习行为，不直接提高能力分，避免把点击操作伪造成能力证据。
- 阶段复测不能手动标记完成；必须从路径发起并完成确定性判分。
- 复测后生成完整的新能力画像，完成关联复测项，归档旧路径，再依据最新 Gap 自动生成新路径。
- 若学生已经达标或 Agent 暂时不可用，画像与归档仍会保存，响应明确说明没有生成新路径。

> **Phase 9 已完成并在首页标记为已上线。** 路径顺序、Gap、判分和进度均由确定性代码计算；
> LLM 只负责学习阶段文案，失败时不会回滚已经成立的测评事实。

---

## 岗位数据（Module 1a）

> ⏳ **待录入真实数据。** 管线已就绪，见 [docs/USER_TODO.md](docs/USER_TODO.md) 第 1 项。

```bash
# 1. 复制模板并填入真实 JD
cp data/seed/job_postings_TEMPLATE.json data/seed/job_postings_ai_data_annotator.json

# 2. 校验（不写库）
python scripts/import_postings.py --file data/seed/job_postings_ai_data_annotator.json --check

# 3. 导入
python scripts/import_postings.py --file data/seed/job_postings_ai_data_annotator.json
```

### 技能需求排名与趋势（Phase 10）

教师端打开 <http://localhost:5173/teacher/market>。导入完成后，导入脚本会自动
用确定性规则重建统计；也可通过页面“重建统计”按钮或以下 API 手动触发：

```bash
POST /api/v1/job-market/ai_data_annotator/analyze
GET  /api/v1/job-market/ai_data_annotator/dashboard?top_n=10
```

分析不调用 LLM：对每条 JD 的 `raw_text` 按技能规范名、编码和别名进行精确匹配，
每个命中保存为 `job_posting_skill.evidence_span`，再物化为全量和月度
`skill_demand_snapshot`。图表严格只读物化快照。

统计口径：

- **需求频率** = 命中该技能原文的去重 JD 数 ÷ 当前岗位全部已导入 JD 数。
- **月度趋势** = 只使用带 `posted_at` 的 JD；缺发布时间的记录仍进入总排名。
- **证据** = 每项技能最多展示 5 条 JD 原文片段及其公开来源链接，无法回链原文就不展示该技能统计。
- **质量提示** = 看板同时显示样本量、真实/DEMO 构成、抽取覆盖率、缺日期、重复正文和低样本（真实样本少于 30 条）警告。

`DEMO` 样本存在时，页面会明确提示“仅用于管线演示，不可作为对外行业结论”；
没有合法公开 JD 时页面显示可解释空态，不制造图表或趋势结论。

### 为什么必须是原文

`raw_text` 要求**原样抄录**，不得改写或概括。技能需求百分比的可信度完全
建立在「每个数字都能点回到某条 JD 的某段原文」之上；一旦原文被改写，
抽取出的 `evidence_span` 就无法与原文对齐，证据链即断——那样算出来的
82% 和编造的没有区别。导入脚本会拦下过短或仍是模板占位的文本。

### 演示数据藏不住

`job_posting.data_flag` 区分 `REAL` / `DEMO`，且 `skill_demand_snapshot`
**分别记录**真实与演示样本数。只要统计里混入演示数据，
`is_demo_contaminated` 即为真，前端必须显示「含演示数据」角标。
这让「拿假数据充场面」在数据结构层面就无法隐藏。

图表还会强制显示样本量 N，口径为「样本分析」而非「行业普查」。

### 隐私

导入时自动抹去手机号、邮箱、微信号、QQ 号，并置 `pii_scrubbed` 标记。
薪资、年份等数字不受影响。

---

## 课程覆盖与岗位能力 Gap（Phase 11）

课程 Gap 不是让模型凭课程名猜“有没有教过”，而是把课程、规范技能和课程原文
证据分别入库。先导入公开方案节选：

```bash
.venv/Scripts/python.exe scripts/seed_curriculum.py
```

教师端打开 <http://localhost:5173/teacher/curriculum-gap>，或调用：

```bash
GET /api/v1/curriculum/ai_data_annotator/gap
GET /api/v1/curriculum/ai_data_annotator/optimization
```

当前默认样例为北京信息职业技术学院 2025 级人工智能技术应用专业（三年制）公开方案的
**4 门已结构化高相关课程节选**，包含 9 条带知识块、页码和原文引句的课程—技能映射。
同库保留河南机电职业学院 2023 级样例供对照。页面会始终显示
“部分结构化”提示：**未映射仅表示当前已结构化范围未发现证据，不等于该方案
一定没有教授该能力。**

课程覆盖层级也刻意保持克制：

- **已提及**：课程正文明确出现相关内容；
- **实践目标**：课程能力目标明确要求学生完成相关实践；
- **未映射**：当前结构化课程中没有该规范技能的原文证据。

这些是课程结构性覆盖，不是学习成效或教学质量评分。岗位需求频率只有在同岗位
公开 JD **真实样本不少于 30 条且不含 DEMO** 时才用于排序；不满足时系统停用
频率排序并给出质量警告。

要替换为本校方案，只需提供 PDF 或公开链接；新增 manifest 后按同一数据结构导入，
无需改动 Gap 计算逻辑。

### 人才培养方案优化（Phase 12）

教师端 `/teacher/curriculum-optimization` 只在岗位样本可靠时生成调整优先级：

`优先级 = 岗位需求频率 × (1 - 课程覆盖比例) × 100`

每项建议携带课程原文证据与可读计算依据。真实 JD 少于 30 条或混入 DEMO 时，
系统停止排序并说明原因，而不是输出看似精确的“优化方案”。

### AI 学习助手（Phase 13）

学生从学习中心点击“AI 学习助手”，或在任一学生实训任务详情点击“向 AI Tutor 提问”进入。
助手服务会持久化会话和消息，并在每次回答中组合：学生最近能力画像、已选实训任务及其步骤、最近 6 条消息和最多 4 条知识库检索依据。

```bash
POST /api/v1/students/{student_id}/tutor/chat
```

请求包含 `job_id`、用户问题，以及可选的 `task_id`、`conversation_id`；响应包含会话 ID、AI 回答、`reasoning_summary`、置信度、低证据提示和 `SourceRef` 引用。服务端会拒绝跨学生、跨岗位或不存在的会话/实训任务，避免上下文串用。知识库没有足够依据时会明确提示，不会伪造来源。

前端支持在同一会话中连续追问；切换当前实训任务会自动新开会话，保证回答只使用对应任务上下文。AI 内容在界面中标明为辅助学习内容，应结合教师指导核验。

### 引用核验层（Phase 14）

所有继承 `BaseAgent` 的结构化 AI 输出，以及 AI Tutor 的回答，都会经过统一的
`CitationVerificationService`：

- 文献引用必须能定位到真实的 `knowledge_chunk.id`；岗位统计引用必须能定位到真实的 `job_posting.id`。
- 服务端用数据库中的来源名称、页码、链接和原文片段回填响应，调用方或模型提供的元数据不会被直接信任。
- 不存在、缺锚点或重复的引用会被排除；输出的 `evidence_sufficiency` 因此变为 `sufficient`、`partial` 或 `insufficient`。
- 每条已核验的“结论 → 证据”关系写入 `citation` 表，并可通过 `GET /api/v1/llm-runs/{run_id}` 审计回查。

`confidence` 现由结构校验结果与可回查证据充分度共同计算，不再把“JSON 符合 Schema”误表述为“专业结论正确”。证据不足时，Tutor 界面会明确显示状态和警示；系统不会补造引文。

### 真实用户测试（Phase 15）

教师端打开 <http://localhost:5173/teacher/user-testing>。该工作台只记录**匿名别名**、
角色、任务观察结果、完成情况、达成度、易用性和反馈；不预填任何测试结果，也不会把
草稿会话纳入汇总。

- 内置两条可复用测试脚本：教师侧“产业需求到实训设计闭环”、学生侧“诊断到自适应学习闭环”。
- 会话必须逐项填写实际结果、完成情况、达成度与易用性后才能结束；结束后记录锁定并进入报告。
- 报告仅基于已完成记录计算完成率、平均达成度、平均易用性和任务级汇总。少于 2 名样本会显示试运行警示；零完成样本不会生成结论。
- 测试记录可由教师删除，便于按用户请求清除数据。

```bash
GET    /api/v1/user-testing/scripts
POST   /api/v1/user-testing/sessions
PATCH  /api/v1/user-testing/tasks/{task_id}
POST   /api/v1/user-testing/sessions/{session_id}/complete
GET    /api/v1/user-testing/report
DELETE /api/v1/user-testing/sessions/{session_id}
```

---

## 技能规范表

全系统唯一 join key，**从国家职业技能标准原文抽取**，不由 AI 凭通用认知起草。

```bash
.venv/Scripts/python.exe scripts/extract_skills.py   # 从标准抽取 → seed 文件
.venv/Scripts/python.exe scripts/seed_skills.py      # seed → skill 表 + 自检
```

当前 26 条技能，覆盖 annotation / data / quality / soft / tool 五类，
每条都能下钻到标准的具体页码与原文引文。

### 三道防伪造闸门

抽取时模型只负责**命名与归类**，技能是否成立由标准原文决定：

| 闸门 | 拦截内容 |
|---|---|
| 引文核验 | `evidence_quote` 必须是来源原文的精确子串（仅容忍空白差异），对不上直接丢弃 |
| 前缀自洽 | `skill_code` 前缀必须与 `category` 一致 |
| 名称可测评 | 拒绝 `general` / `basic` / `labeling` 这类无法命题的空泛名称 |

模型可以幻觉出技能名，但**编不出对应的原文** —— 实测拦下了 3 条凭空生成的候选。

### 范围界定

只抽国标的**五级/初级工 + 四级/中级工**（高职毕业生入职层），
截断于「3.3 三级/高级工」之前。三级及以上是带徒培训、系统设计、业务规划，
属职业晋升路径；全抽会产出 86 条技能，其中 27 条是学生根本不需要测评的
「培训」「业务规划」类维度。

### 人工策展可审计

模型逐块抽取时看不到其他块，必然产生跨块近义重复。这些合并决定写在
[knowledge/skill_overrides.json](knowledge/skill_overrides.json)，
每条附理由，按书写顺序应用（rename / merge / exclude）——
而不是悄悄手改生成结果。合并时保留全部来源引用，消重不丢证据。

> `provenance` 一律为 `llm_drafted`。**真实教师签字前不得标为
> `human_reviewed`** —— 测试中有断言强制这一点。

### 归一化

`Label Studio` / `LabelStudio` / `label-studio` / `ＬａｂｅｌＳｔｕｄｉｏ`
必须归到同一个 `skill_code`，否则 Gap Analysis 会**静默算错**。

匹配顺序不可颠倒：精确编码 → 归一化别名 →（Phase 4）向量近邻 → LLM 兜底。
**匹配不上就返回 `unmatched`，绝不猜** —— 硬塞一个最像的技能会污染整张
能力表且无从察觉。载入种子时会自检别名是否撞车，撞车即报错退出。

---

## 技术栈

**后端**：Python 3.10 · FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2
**RAG**：Chroma（向量）+ rank-bm25/jieba（稀疏）→ RRF 混合检索 ·
本地 `BAAI/bge-small-zh-v1.5` embedding
**LLM**：OpenAI 兼容接口（DeepSeek / 通义 / OpenRouter），Provider 可插拔
**前端**：React 19 · TypeScript · Vite · Ant Design 6 · ECharts 6 ·
TanStack Query · Zustand · React Router

刻意**不使用**：LangChain、图数据库、Redis、Celery、任何 Agent 编排框架。
当前规模下它们只增加复杂度，不带来收益。

---

## 目录结构

```
challenge_cup/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI 入口
│   │   ├── api/v1/              路由
│   │   ├── agents/              各业务 Agent（Phase 3 起逐步填充）
│   │   ├── rag/                 检索链路（Phase 4）
│   │   ├── services/            业务编排 + 确定性计算
│   │   ├── schemas/             Pydantic 契约
│   │   ├── models/              SQLAlchemy ORM
│   │   └── core/                配置 / 数据库 / 枚举 / 日志 / 异常
│   ├── tests/
│   └── requirements.txt
├── frontend/src/
│   ├── pages/  components/  charts/  services/  types/
├── knowledge/                   原始资料，按来源类型分目录
├── data/
│   ├── seed/                    演示数据（带 DEMO 标记）
│   └── skilltwin.db             SQLite（不进版本库）
├── scripts/                     reset_db 等运维脚本
├── docs/
└── .env.example
```

---

## 数据库核心表（节选）

| 表 | 作用 |
|---|---|
| `skill` | **规范技能表**，全系统 join key 的载体 |
| `job` | 岗位 |
| `competency_graph` | 图谱版本（draft / approved / archived） |
| `competency_node` | 图谱节点，树形结构 |
| `competency_edge` | 跨层关系，`prereq` 边是学习路径拓扑排序依据 |
| `knowledge_doc` | 知识库文档（来源字段必须可核验） |
| `knowledge_chunk` | 检索与引用的最小单元 |
| `llm_run` | 模型调用审计 —— 可复现 / 可回放 / 可解释的底座 |
| `citation` | 结论 → 证据的锚定记录 |
| `tutor_conversation` | 学生、岗位与可选实训任务绑定的 Tutor 会话 |
| `tutor_message` | 会话消息、回答所用证据与关联的 `llm_run` |
| `user_test_session` | 真实用户测试的匿名会话与整体反馈 |
| `user_test_task_record` | 会话内逐项任务的实际结果、量表与反馈 |

后续 Phase 会追加 `job_posting` / `course` / `training_task` /
`assessment` / `skill_profile` / `learning_path` 等表。

---

## 安全与合规

- `.env`、`data/*.db`、`data/chroma/` 已在 `.gitignore` 中
- **API Key 只从环境变量读取，绝不硬编码、绝不入库**
- 学生数据全部化名，不含真实个人信息，且支持彻底删除
- AI 生成内容在前端带「AI 生成」标识，低置信度显式提示
- 岗位数据仅使用合法公开信息，记录来源 URL 与许可说明
