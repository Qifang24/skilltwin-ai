# SkillTwin AI 全部部署在 Vercel

本仓库使用 [Vercel Services](https://vercel.com/kb/guide/vercel-services)：`frontend/` 的 Vite 页面和 `backend/` 的 FastAPI 共用一个 Vercel 项目、一个 HTTPS 域名。`vercel.json` 将 `/api/*` 交给后端，其余请求交给前端。前端无需设置 `VITE_API_BASE_URL`，也无需另行处理 CORS。

数据库不是放在 Function 的本地磁盘上，而是通过 Vercel Marketplace 连接托管 Postgres（建议 Neon）。课程上传文件和小型知识库向量持久保存在这个数据库。Vercel 的 Function 文件系统不适合持久化 SQLite、Chroma 或上传文件；本地 Docker 模式仍可使用它们。

## 1. Vercel 项目设置

当前 Vercel 项目是 `skilltwin-ai`（团队 `chien-bots-projects`）。在 **Settings → Build and Deployment** 确认：

- Framework Preset：**Services**，不是 Vite 或 FastAPI；
- Root Directory：仓库根目录 `.`；
- 清除以前项目级自定义的 Build Command、Install Command 和 Output Directory，使每个服务按自己的配置构建；
- Git Production Branch：`kl`（当前代码所在分支）。

部署配置位于根目录 `vercel.json`，其中前端服务的 rewrite 为 React Router 深链接提供 SPA fallback；`backend/server.py` 是 Python 入口，`backend/requirements.txt` 只包含云端必要依赖。`frontend/vercel.json` 供单独部署前端时使用。

## 2. 建立持久数据库

在 Vercel 项目的 **Storage → Create Database → Neon** 选择适合的方案、数据库区域，然后连接到 `skilltwin-ai`。Neon 的 Vercel 集成通常会自动注入 `DATABASE_URL`；请在 **Settings → Environment Variables** 核实 Production 和 Preview 环境均能使用。数据库区域尽量靠近 Vercel Function 区域。[Vercel Marketplace 存储说明](https://vercel.com/docs/marketplace-storage)

不要把数据库 URL、SQL 用户名密码或 API Key 写进 Git、`frontend/.env` 或任何 `VITE_*` 变量。它们只能留在 Vercel 环境变量中。`VITE_*` 会进入浏览器产物。

## 3. 环境变量

在同一个 Vercel 项目的 **Settings → Environment Variables** 配置以下变量，并选择 Production、Preview。旧项目已有的 `LLM_*`、`SPARK_*` 等值可以保留，但需检查是否真的可用。

| 变量 | 值或用途 |
| --- | --- |
| `DATABASE_URL` | Neon 注入的 PostgreSQL 连接串；必需 |
| `VECTOR_STORE` | `sql`；必需 |
| `FILE_STORAGE` | `database`；必需 |
| `EMBEDDING_PROVIDER` | `openai_compat`；必需，Vercel 不加载本地 BGE/torch |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small`（OpenRouter 模型 ID） |
| `EMBEDDING_DIM` | `1536` |
| `EMBEDDING_BASE_URL` | `https://openrouter.ai/api/v1` |
| `EMBEDDING_API_KEY` | 云端同为 OpenRouter 时可复用后端的 `LLM_API_KEY`；本地建立索引时临时提供，勿写入源码 |
| `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` | 聊天/生成模型配置；仅后端使用 |
| `VITE_UPLOAD_MAX_MB` | `4`；与 Vercel Function 的请求体限制相配 |
| `RETRIEVE_DENSE_TOP_K` | `20`；向量与数据库 BM25 关键词检索并用 |

语义检索直接调用 [OpenRouter Embeddings API](https://openrouter.ai/docs/api/api-reference/embeddings/create-embeddings)，无需开通 Vercel AI Gateway；聊天模型与 embedding 模型是两个独立配置。先运行 `scripts/bootstrap_vercel.py --step index` 为已有知识块建立向量，再设置 `RETRIEVE_DENSE_TOP_K=20` 并重新部署。云端运行期可复用 Vercel Secret 中的 OpenRouter `LLM_API_KEY`，本地构建时需临时传入 `EMBEDDING_API_KEY`。所有真正的密钥应在 Vercel 中设为 Sensitive，切勿写入 Git 或聊天记录。

## 4. 初始化数据库和数据

第一次部署前，先在本机完成数据库迁移和种子数据导入。不要在每次 Function 启动时重复爬取文档或生成 embedding。仓库中的 `data/seed/` 有技能与岗位样例，但 `knowledge/` 只提交了来源清单，没有原始 PDF；若不补齐来源文件，RAG 与课程引用无法完整工作。

Vercel CLI 可以临时注入 Marketplace 的 `DATABASE_URL` 和项目 OIDC Token 来初始化数据库，不必把连接串复制到聊天或源码。已标记为 Sensitive 的旧变量无法被 CLI 读回，`scripts/bootstrap_vercel.py` 会在本地清理它们的占位值，再运行迁移、种子导入、知识摄取和索引构建。

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt 'alembic>=1.14,<2'
npx vercel@latest link --yes --project skilltwin-ai --scope chien-bots-projects
npx vercel@latest env run -e production -- .venv/bin/python scripts/bootstrap_vercel.py --skip-index
```

知识数据准备好后，在本机临时提供 OpenRouter 的 `EMBEDDING_API_KEY`，再运行
`npx vercel@latest env run -e production -- .venv/bin/python scripts/bootstrap_vercel.py --step index`。
Vercel CLI 不会把已标记为 Secret 的 `LLM_API_KEY` 下载到本机，所以构建索引时需要这个临时变量；
云端检索则继续使用 Vercel 中的 Secret。先核对所有知识块已有向量，再将 `RETRIEVE_DENSE_TOP_K` 设为 `20`。

脚本会读取仓库中的 `knowledge/` PDF。首次运行前，先按 `knowledge/manifest.json` 的 `source_url` 下载并核对每份 PDF，保存到相应 `knowledge/...` 路径。PDF 被 `.gitignore` 排除，不会进入 Vercel Function；解析后的知识块与向量会存到 Postgres。脚本可重复运行，已导入且未变化的文档会跳过。

`seed_curriculum.py` 需要其引用的知识块已存在；若下载的文档版本不同，脚本会因证据不匹配而拒绝导入，应核对原文，不要跳过校验。知识库目前规模较小，SQL 向量检索会逐条扫描，未来语料大幅增长时应迁移到 pgvector 或专用向量存储。

## 5. 部署与检查

推送 `kl` 分支后，Vercel 会按项目设置自动部署。也可在仓库根目录运行 `npx vercel@latest` 做 Preview，验证后运行 `npx vercel@latest --prod`。部署完成后检查：

1. `https://你的项目.vercel.app/api/v1/health` 返回健康状态；
2. `https://你的项目.vercel.app/teacher` 可直接打开并刷新；
3. 浏览器 Network 中 `/api/v1/*` 请求返回成功，且不需要跨域请求；
4. 上传一份不超过 4 MB 的课程文件，刷新后仍能继续解析/确认。

Vercel Function 的请求与响应体有 [4.5 MB 上限](https://vercel.com/docs/functions/limitations)，所以大型文件需改用对象存储直传。当前 API 没有登录鉴权，包含写入、删除和模型调用接口；公开给不受信任用户之前，应启用 Vercel Deployment Protection 或实现身份验证与权限控制。数据库、模型 API 和 Vercel Functions 的免费额度与计费规则以各平台控制台为准。
