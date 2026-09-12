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

- 模型调度：Ollama 单槽位热切换、显存值守（按需 load/unload）、模型状态页（当前/已加载/最近切换事件）
- `@` 接力协作：消息中 `@` 其他智能体，跨模型串行接力，消息标注智能体归属
- 多模态图片理解：上传图片自动切换到 `qwen2.5vl:7b`，回答结合图片内容（VL 模型按需加载）

## 快速开始

1. 安装依赖：Docker Desktop、Ollama（`OLLAMA_MODELS` 指向数据盘）、uv（Python 3.12+）、Node 20+ / pnpm
2. 拉取模型：`ollama pull qwen2.5:7b-instruct-q4_K_M`；M4 演示另需 `ollama pull deepseek-r1:latest` 与 `ollama pull qwen2.5vl:7b`（调度器按需加载，显存不足时自动换出）
3. 起基础设施：`docker compose up -d`
4. 起后端：`cd backend && uv sync && uv run alembic upgrade head && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000`
5. 起解析 worker（新终端）：`cd backend && uv run arq app.workers.settings.WorkerSettings`（上传文档需要 worker 运行）
6. 起前端：`cd frontend && pnpm i && pnpm dev` → http://localhost:5173（演示账号 demo / Demo123456）

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

## 文档

- 设计文档：`docs/设计/`
- 实施计划：`docs/superpowers/plans/`
