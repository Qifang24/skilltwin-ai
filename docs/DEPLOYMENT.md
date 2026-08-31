# Phase 17：Docker 部署手册

本项目采用单域名容器部署：浏览器访问 Nginx，Nginx 将 `/api/*` 反向代理到 FastAPI。
因此前端继续使用相对 API 路径，不需要把后端公网地址或密钥编译进前端产物。

```
Browser → Nginx / React (8080) → FastAPI (container-only :8000) → SQLite + Chroma named volume
```

## 部署前检查

1. 安装 Docker Desktop（本地）或准备支持 Docker Compose 与持久化磁盘的云主机。
2. 复制 `.env.example` 为 `.env`，仅在 `.env` 中填入真实 `LLM_API_KEY` 等密钥。
3. 将 `CORS_ORIGINS` 替换为最终访问域名；同源代理本身不依赖 CORS，但直接访问 API 时需要。
4. 生产环境请使用 HTTPS 终止层（云负载均衡或反向代理），不要把裸 HTTP 直接暴露到公网。

不要将 `.env`、`data/skilltwin.db`、`data/chroma` 或备份文件提交到版本库。

## 启动

```powershell
Copy-Item .env.example .env
# 编辑 .env：填入真实 LLM 配置，并设置正式域名的 CORS_ORIGINS
docker compose up --build -d
docker compose logs -f backend
```

访问 `http://localhost:8080`。首次启动会依次创建表、将镜像内的版本化技能/课程 seed 复制到持久卷、载入种子数据、摄取
知识库并建立向量和 BM25 索引。若本机尚无 BGE 模型，首次下载及建索引会明显更慢；健康检查
为此预留了 180 秒启动窗口。完成后会在数据卷创建两个 bootstrap 标记，后续重启不会重复建索引。

如只想先验证 Web 与数据库链路，可在 `.env` 中设置：

```env
BUILD_RAG_INDEX_ON_START=false
```

这种模式不适合作为 RAG 功能演示或正式比赛提交；恢复为 `true` 后重启即可补建索引。

## 运行与验收

```powershell
docker compose ps
docker compose logs --tail=100 backend
docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').read().decode())"
```

浏览器验收入口：

- `http://localhost:8080/`：首页与教师/学生入口。
- `http://localhost:8080/teacher`：岗位图谱、市场、课程 Gap、实训与测试工作台。
- `http://localhost:8080/docs`：仅建议在受保护的评审环境开放 API 文档。

## 数据持久化与备份

`skilltwin_data` 是唯一运行数据卷，包含 SQLite、Chroma、BM25 索引和 bootstrap 标记。
本地 embedding 模型缓存也落在其中，升级镜像或重启容器不会重复下载模型。部署前、比赛前和修改知识库前都应备份：

```powershell
New-Item -ItemType Directory -Force backups
docker compose cp backend:/app/data/skilltwin.db ./backups/skilltwin.db
# 如需完整备份 Chroma，请按宿主机 Docker 卷备份流程导出 skilltwin_data。
```

恢复 SQLite 时先停止前端写入，并确认目标文件来自可信备份；不要覆盖不明来源的数据卷。

## 云端落地边界

本 MVP 使用 SQLite + Chroma，必须部署在**带持久化卷的长驻容器/虚拟机**上；不适合无状态函数
平台。建议至少预留 4 GB 内存和 10 GB 持久化磁盘。若使用 CPU embedding，首次建索引比本地 GPU
更慢；比赛现场更推荐预热并备份 `skilltwin_data`，再以 `DEMO_MODE=replay` 运行已录制的真实结果。

本仓库不会也不能替用户创建云账号、配置域名或写入线上密钥。获得目标云平台权限后，可在其
支持 Docker Compose 的运行环境中直接使用本文件部署。
