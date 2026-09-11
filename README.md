# 多智能体 AI 专家工作台

本地部署的多智能体网站：`/` 技能面板、`@` 接力协作、知识库引用溯源、模型显存调度与可观测性。

## 功能（M1 会话）

- 会话持久化：消息与服务端同步，刷新后完整恢复（含 blocks/思考链）
- 会话侧边栏：搜索分组、置顶、重命名、归档、删除
- 消息操作：停止、重新生成、编辑重发、有用/无用评分
- 标题自动生成：首轮对话后由模型生成会话标题

## 快速开始

1. 安装依赖：Docker Desktop、Ollama（`OLLAMA_MODELS` 指向数据盘）、uv（Python 3.12+）、Node 20+ / pnpm
2. 拉取模型：`ollama pull qwen2.5:7b-instruct-q4_K_M`
3. 起基础设施：`docker compose up -d`
4. 起后端：`cd backend && uv sync && uv run alembic upgrade head && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000`
5. 起前端：`cd frontend && pnpm i && pnpm dev` → http://localhost:5173（演示账号 demo / Demo123456）

## 演示数据

```powershell
cd backend
uv run python -m scripts.seed                 # 创建 demo / Demo123456
uv run python -m scripts.seed_demo_sessions   # 为 demo 用户创建 1000 个会话与一组演示问答
```

用于验证侧边栏千级会话下的滚动、搜索与切换性能。

## 文档

- 设计文档：`docs/设计/`
- 实施计划：`docs/superpowers/plans/`
