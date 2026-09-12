# 多智能体 AI 专家工作台

本地部署的多智能体网站：`/` 技能面板、`@` 接力协作、知识库引用溯源、模型显存调度与可观测性。

## 功能（M1 会话）

- 会话持久化：消息与服务端同步，刷新后完整恢复（含 blocks/思考链）
- 会话侧边栏：搜索分组、置顶、重命名、归档、删除
- 消息操作：停止、重新生成、编辑重发、有用/无用评分
- 标题自动生成：首轮对话后由模型生成会话标题

## 功能（M2 智能体）

- 智能体管理：系统提示词（支持 `{{today}}` 变量）/参数/工具绑定/版本发布与回滚
- 工具调用：内置 `time_now`（当前时间）；`kb_search`（知识库混合检索，见 M3）
- 选择智能体对话：新建会话时选择智能体，按绑定工具自动进入工具循环
- 欢迎语与示例问题：智能体会话展示欢迎语与可点击的示例问题

## 功能（M3 知识库）

- 知识库：上传（pdf/md/txt/docx）/解析/切片/嵌入流水线与文档状态徽章、失败重试
- 混合检索：pgvector 向量检索 + jieba 全文检索（FTS）+ RRF 融合
- 回答引用：引用角标、回答依据与来源抽屉
- 智能体知识库绑定：为智能体绑定知识库并设置 top_k

## 功能（M4 模型调度与协作）

- 模型调度：Ollama 单槽位热切换、显存值守（按需 load/unload）、模型状态接口（GET /api/v1/models/status：当前/已加载/最近切换事件/显存快照与曲线数据，Ollama 不可用时降级回退最近快照）
- `@` 接力协作：消息中 `@` 其他智能体，跨模型串行接力，消息标注智能体归属
- 多模态图片理解：上传图片自动切换到 `qwen2.5vl:7b`，回答结合图片内容（VL 模型按需加载）

## 功能（M5 可观测性）

- 全链路埋点：统一 spans 表覆盖 llm / tool / retrieval / model_switch，trace_id = 助手消息；观测写入批内合并、失败不影响生成
- HTTP 计数：中间件内存按分钟聚合，定时批量落库（不产生每请求写库开销）
- 全局仪表盘（`/admin`）：请求/Token/错误率/p95/模型切换/工具/检索/显存曲线，24h~30d 范围切换
- 会话详情（`/admin/sessions/:id`）：span waterfall + input/output JSON 抽屉 + 工具日志筛选与 CSV 导出
- M4 遗留清偿：模型状态降级（Ollama 不可用回退最近快照）、接力停止语义（排队回合可取消）、会话切换重置 Composer 草稿/提及、孤儿附件 TTL 清理
- 告警（按计划砍除，延后）：`alert_rules` 阈值规则 + ARQ 每分钟评估 + 站内铃铛红点/横幅未实现；数据表已随迁移建好但无对应 API/UI，详见「已知延后项」

## 快速开始

1. 安装依赖：Docker Desktop、Ollama（`OLLAMA_MODELS` 指向数据盘）、uv（Python 3.12+）、Node 20+ / pnpm
2. 拉取模型：`ollama pull qwen2.5:7b-instruct-q4_K_M`；M4 演示另需 `ollama pull deepseek-r1:latest` 与 `ollama pull qwen2.5vl:7b`（调度器按需加载，显存不足时自动换出）
3. 起基础设施：`docker compose up -d`
4. 起后端：`cd backend && uv sync && uv run alembic upgrade head && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000`
5. 起解析 worker（新终端）：`cd backend && uv run arq app.workers.settings.WorkerSettings`（上传文档需要 worker 运行）
6. 起前端：`cd frontend && pnpm i && pnpm dev` → http://localhost:5173（演示账号 demo / Demo123456；登录后左下角「📊 可观测性」进入 `/admin`）

## 演示数据

```powershell
cd backend
uv run python -m scripts.seed                 # 创建 demo / Demo123456
uv run python -m scripts.seed_agents          # 创建 4 个预置智能体（通用助手 / 代码专家 / 时间管家 / 深度思考）
uv run python -m scripts.seed_demo_sessions   # 为 demo 用户创建 1000 个会话与一组演示问答
uv run python -m scripts.seed_kb              # 创建演示知识库「Java 并发笔记」并绑定到「代码专家」（幂等）
```

`seed_demo_sessions` 用于验证侧边栏千级会话下的滚动、搜索与切换性能；`seed_kb` 首次运行会真实解析、切片并用 bge-m3 嵌入演示文档。

「深度思考」预置使用 `deepseek-r1:latest`，便于演示接力玩法：在「代码专家」会话里提问并 `@深度思考`，会话将串行调用两个模型（qwen2.5 → deepseek-r1），消息标注各自智能体，推理模型的回答带思考链；上传图片提问则自动切换到 `qwen2.5vl:7b`。

问完一轮后，聊天页智能体标题栏的「查看调用链」可下钻该条回答的 span waterfall（llm / tool / retrieval / model_switch）与 input/output JSON；左下角「📊 可观测性」进入 `/admin` 查看全局指标（数据来自 spans 与分钟级 HTTP 计数）。

## 30 秒演示（可观测性）

前置：`docker compose up -d`；后端 `cd backend && uv run alembic upgrade head && uv run uvicorn app.main:app --reload --port 8000`；另开终端跑 `uv run arq app.workers.settings.WorkerSettings`（知识库解析需要）；前端 `cd frontend && pnpm dev`；用 demo / Demo123456 登录。

1. 产生调用链：进入「代码专家」会话，提一个知识库问题并 `@深度思考` 接力，另上传一张图片提一个问。预期：接力输出两条助手消息（各自标注所属智能体），其间出现模型切换提示（qwen2.5 → deepseek-r1；图片回合切换到 `qwen2.5vl:7b`）；一轮问答产生 llm / tool（kb_search）/ retrieval / model_switch 四类 span。
2. 核对聚合指标：请求 `GET /api/v1/admin/metrics/overview?hours=24`（Swagger 或带登录态）。预期：`cards.llm_calls ≥ 3`、`cards.model_switches ≥ 1`、`cards.retrieval_calls ≥ 1`、`cards.prompt_tokens > 0`、`http.requests > 0`。
3. 全局仪表盘：左下角「📊 可观测性」进入 `/admin`。预期：指标卡片与请求/Token 趋势、智能体活跃排行、Token 分布、显存曲线均有数据；切「7 天」不报错。
4. 会话调用链：回到聊天页，点智能体标题栏「查看调用链」进入 `/admin/sessions/:sessionId`（左侧默认选中最新助手消息，可切换）。预期：waterfall 出现 llm / tool / retrieval 条（接力/图片回合含 model_switch）；点 tool 条，抽屉展示 input/output JSON 树与耗时。
5. 筛选与导出：在会话详情「工具日志」区筛选 type=tool、status=ok，点「导出 CSV」。预期：文件用 Excel 打开无中文乱码（UTF-8 BOM），行数与筛选结果一致。

> 原第 6 步（告警规则 + 评估 + 站内通知）已按计划砍除，见下方「已知延后项」。

## 已知延后项（不在 M5 范围，记录备查）

- **告警规则 + 评估任务 + 站内通知（Task 10，按计划有意砍除）**：M5 计划与开发路线图均将本项标注为【可砍】，收尾时按砍项优先级决定跳过，非遗漏；迁移已建好 `alert_rules` / `alert_events` 表（闲置无害）。阈值规则 API、ARQ 每分钟评估、仪表盘铃铛红点/横幅留待 M6.x 或 Phase 2 复活。设计 08.5 明确不做的告警 webhook 预留字段、短信/钉钉通知同列于此。
- **`mv_metrics_hourly` 物化视图未启用**：设计 08.4 的 MV 是规模化优化；M5 以等价的即时聚合 SQL（`date_trunc('hour')` + `percentile_cont` + `FILTER`，走 `idx_spans_agg`）实现，换来精确的 p95 重聚合与天然的多用户过滤；个人规模（90 天保留）下无性能问题。MV + 每分钟 REFRESH 留作 M6/Docker 部署优化项。
- **成本三视角（等效 $ / 显存成本切换 chip）**：依赖 `models.reference_price_in/out` 注册表（设计 02 的 `models` 表尚未建），M5 指标口径为 Token 量 + GPU 时间。
- **数据保留清理任务**（spans 90 天 / model_events 30 天 / HTTP 计数 7 天每日清理）：与 M6 运维/Docker 一起做。
- **后台「模型管理」页**（手动 load/unload 按钮）与 `/api/v1/models/{name}/load|unload`（设计 07.6）：M5 仪表盘只读展示显存曲线。
- **多 worker 一致性**：`CANCEL_SESSIONS` / ModelManager / HTTP 内存计数当前按单 worker 假设（uvicorn 单进程），与 M4 已知限制一致。
- 思考链折叠 UI、OpenAI 兼容端点、Docker 化、虚拟滚动打磨：M6。

## 文档

- 设计文档：`docs/设计/`
- 实施计划：`docs/superpowers/plans/`
