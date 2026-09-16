# 13 · 外部能力接入：MinerU 文档解析 与 联网搜索 MCP

> 状态：设计已定，实施中
> 关联：`05-知识库RAG.md`（文档解析流水线）、`12-扩展能力与MCP.md`（MCP 接入机制）

## 13.1 背景与目标

现有知识库解析只有 `app/ai/rag/parsers.py`：PDF 用 pymupdf 抽纯文本、DOCX 用 python-docx 抽段落，**没有 OCR**——扫描件会直接报「解析结果为空（可能是扫描件）」；表格、公式、多栏排版都丢失。

目标：

1. 用 **MinerU** 替代 PDF / DOCX 的解析与 OCR，产出结构化 Markdown（保留标题、表格、公式）。
2. 用 **open-websearch** 提供**联网搜索 MCP**，让智能体可以真正搜索网络。

## 13.2 决策（已确认）

| 事项 | 决策 |
|---|---|
| MinerU 部署 | **宿主机独立服务**（独立 venv + `mineru-api`），后端经 HTTP 调用；不装进后端镜像 |
| MinerU 数据 | 全程本地，不使用 mineru.net 云 API |
| web-search 运行 | **docker compose 服务 + http MCP** |
| web-search 接入 | 只起服务与文档；由用户在「扩展能力 → MCP」**手动新建并测试连接**（不自动 seed） |

## 13.3 架构

```
知识库上传 ──→ ARQ worker ──→ run_ingest
                                  ├─ MinerU 可用？ ──是──→ mineru_client ──HTTP──→ mineru-api(宿主机:8001) ──→ Markdown
                                  └─ 否 / 失败 ───────────→ parsers.extract_text（旧逻辑，回退）
                                  └─ split → embed → ready

智能体对话 ──→ AgentRuntime ──→ MCP 工具 mcp__web_search__search
                                      └──HTTP──→ web-search 容器(:3000/mcp)
```

## 13.4 MinerU 集成

### 13.4.1 部署（宿主机）

- 独立 venv（放 D/E 盘，避免占用 C 盘），装 `uv pip install -U "mineru[all]"`。
- 预下模型（避免首次解析请求超时；本项目用 `pipeline` 后端即可）：
  `mineru-models-download -s modelscope -m pipeline`
- 启动：`mineru-api --host 0.0.0.0 --port 8001`（`scripts/start-mineru.ps1` 封装）。
- 国内网络设 `MINERU_MODEL_SOURCE=modelscope` 便于下模型；首次运行会下载模型（GB 级）。
- GPU 加速需自行安装与 CUDA 匹配的 torch；否则用 `-b pipeline` 纯 CPU。

### 13.4.2 后端接入

- 新增 `app/ai/rag/mineru_client.py`：
  - `parse(path, file_type) -> list[tuple[int | None, str]]`，与现有 `extract_text` 同签名，便于替换。
  - 调 `POST {MINERU_API_URL}/file_parse`（multipart：`files`、`return_md=true`、`backend=pipeline`），按**实测响应**提取 Markdown。
  - **实测（MinerU 3.4.5）**：成功返回 `{"status":"completed","results":{"<file>":{"md_content":"..."}}}`；失败返回非 2xx（常见 409）且带 `{"status":"failed","error":"..."}`。
  - ⚠️ 默认 backend 是 `hybrid-engine`，**需要 CUDA**；我们装的是 CPU 版 torch，必须显式传 `backend=pipeline`，否则报 `CUDA is not available.`（由 `MINERU_BACKEND` 控制，默认 `pipeline`）。
  - 超时独立配置（默认 300s，解析是分钟级任务）。
- `app/ai/rag/pipeline.py`：`extract_text` 前先尝试 MinerU；**未配置或抛错则回退**旧解析并记 `warning` 日志，保证"装了更好，不装也能用"。
- 支持类型：`pdf` / `docx` 走 MinerU；`md` / `txt` 维持原样。
- 页码：MinerU 输出为整篇 Markdown，无稳定页码 → 统一 `page=None`（引用不显示页码；后续如需可解析 `content_list.json` 恢复）。

### 13.4.3 配置

| 变量 | 默认 | 说明 |
|---|---|---|
| `MINERU_API_URL` | 空 | 为空=不启用 MinerU，走旧解析。Docker 里填 `http://host.docker.internal:8001`；本地开发填 `http://localhost:8001` |
| `MINERU_TIMEOUT_S` | 300 | 单文档解析超时 |
| `MINERU_BACKEND` | `pipeline` | 解析后端；`pipeline` 支持纯 CPU，`hybrid`/`vlm` 需要 CUDA |

### 13.4.4 状态展示

- 新增 `GET /api/v1/capabilities/parser`：返回 `{enabled, api_url, backend, healthy, version, latency_ms, error}`，后端探测 MinerU `/health`（5s 超时），未配置时直接说明回退。
- 前端「扩展能力 → 解析」标签（`ParserPanel`）展示：服务状态徽章（服务正常/连接失败/未启用）、解析后端、服务地址、健康探测耗时、版本与失败原因；30s 轮询。


## 13.5 联网搜索 MCP 集成

- compose 新增服务 `web-search`（镜像 `ghcr.io/aas-ee/open-web-search:latest`，容器内端口 3000，`MODE=http`）。
  - 宿主端口默认映射到 **3300**（3000 落在 Windows 保留段 2929–3028，会 bind 失败；可用 `WEB_SEARCH_PORT` 覆盖）。
- MCP 表单填写：
  - 名称：`web-search`
  - 连接方式：`http`
  - URL：**Docker 后端**用 `http://web-search:3000/mcp`（容器网络内部端口固定 3000）；**宿主机测试 / 本地开发**用 `http://localhost:3300/mcp`
  - 请求头：无（该服务无需鉴权）
- 「测试连接」应列出 `search`、`fetchGithubReadme`、`fetchCsdnArticle`、`fetchJuejinArticle` 等工具。
- 在智能体编辑器「扩展能力」里勾选需要暴露给模型的 tool（如仅 `search`）。

## 13.6 测试

- `mineru_client` 单测：成功（mock HTTP 响应）、超时、非 2xx、响应结构异常。
- pipeline：MinerU 可用路径、MinerU 失败回退路径、未配置路径。
- compose：`web-search` 服务存在且端口/环境变量正确（并入 `test_deploy_config`）。

## 13.7 已知限制

- 首次安装与首次运行需要下载依赖与模型（GB 级、耗时），且依赖联网。
- Windows 的 CUDA 加速需手动装匹配 torch；否则纯 CPU 的 `pipeline` 后端较慢。
- `mineru-api` 任务状态在单进程内存中，重启/多进程不保留（我们用同步 `file_parse`，影响有限）。
- 纯文本 PDF 的提升有限；扫描件 / 复杂版式收益最大。

## 13.8 决策记录

- MinerU 用宿主机独立服务，不污染后端镜像（用户确认）。
- web-search 用 Docker 服务 + http，而非 stdio（用户确认）。
- MCP 配置手动添加，不自动 seed（用户确认）。
