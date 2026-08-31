# Phase 18：科大讯飞星火 / 星辰 Agent 平台适配

本项目保留本地 RAG、证据核验、LLM 调用审计和 `DEMO_MODE=replay`，只把最终模型调用
替换为可配置的讯飞 Provider。不会把本地知识库无提示地上传到第三方平台。

## 1. 星火 HTTP 模型 Provider

在 `.env` 中设置：

```env
LLM_PROVIDER=spark
SPARK_BASE_URL=https://spark-api-open.xf-yun.com/v1
SPARK_MODEL=4.0Ultra
SPARK_API_PASSWORD=仅填控制台的 HTTP APIPassword
```

系统以 OpenAI-compatible 方式调用星火 HTTP `/chat/completions`，因此现有结构化 Agent、
JSON 修复、`llm_run` 审计和缓存回放无需改动。`SPARK_API_PASSWORD` 是 HTTP 接口凭证；
不要把 WebSocket 的 `APPID/APIKey/APISecret` 填到这里。

依据：讯飞官方 HTTP 文档说明该接口地址为
`https://spark-api-open.xf-yun.com/v1/chat/completions`，使用 Bearer APIPassword，且兼容
OpenAI SDK。[官方 HTTP 文档](https://www.xfyun.cn/doc/spark/HTTP%E8%B0%83%E7%94%A8%E6%96%87%E6%A1%A3.html)

## 2. 星辰 Agent Workflow Provider

先在星火智能体创作中心创建、调试并**发布**工作流。工作流开始节点需要有一个文本输入；默认
参数名为 `AGENT_USER_INPUT`，可通过 `XINGCHEN_INPUT_PARAMETER` 修改。

```env
LLM_PROVIDER=xingchen_workflow
XINGCHEN_FLOW_ID=已发布工作流 ID
XINGCHEN_API_KEY=工作流 API Key
XINGCHEN_API_SECRET=工作流 API Secret
XINGCHEN_INPUT_PARAMETER=AGENT_USER_INPUT
XINGCHEN_UID=skilltwin-demo
```

适配器以非流式方式传递完整的 system/user/assistant 上下文（带角色标记），请求体为
`flow_id`、`parameters`、`stream=false` 和可选 `uid`；凭证按 `Bearer API_KEY:API_SECRET`
发送。平台响应的 `code != 0`（包括“工作流仍为草稿”）会被明确记录为调用失败，而不会生成
替代答案。

依据：讯飞官方 Workflow OpenAPI 要求工作流先创建、调试并发布，端点为
`https://xingchen-api.xf-yun.com/workflow/v1/chat/completions`，认证格式为
`Bearer {API_KEY}:{API_SECRET}`；官方也展示了 `stream=false` 的非流式响应。
[官方 Workflow 文档](https://www.xfyun.cn/doc/spark/workflow.html)

## 3. 结构化 Agent 与安全边界

- 工作流本身不等同于 JSON mode。若将其用于能力图谱、实训任务等结构化 Agent，必须在平台
  工作流中保留“只输出目标 JSON”的指令；本系统仍会进行 Pydantic 校验和一次修复。
- 现有本地 RAG 是默认事实依据。若你在星辰平台额外挂载知识库，应单独进行资料授权、来源
  一致性和引用核验，不能把平台输出自动视为已验证证据。
- 密钥只存在 `.env` 或云平台 Secret；`health` 接口仅检查配置齐备性，不会发送测试请求。
- 比赛现场优先使用已录制的 `DEMO_MODE=replay`；它不会发起讯飞网络调用，也不会伪造结果。

## 4. 验收

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest tests/test_xfyun_providers.py -vv
```

真实冒烟测试会消耗平台额度，必须由持有讯飞账号和发布工作流权限的人在填入密钥后主动执行。
