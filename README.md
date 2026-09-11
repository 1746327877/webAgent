# 多智能体 AI 专家工作台

本地部署的多智能体网站：`/` 技能面板、`@` 接力协作、知识库引用溯源、模型显存调度与可观测性。

## 快速开始

1. 安装依赖：Docker Desktop、Ollama（`OLLAMA_MODELS` 指向数据盘）、uv（Python 3.12+）、Node 20+ / pnpm
2. 拉取模型：`ollama pull qwen2.5:7b-instruct-q4_K_M`
3. 起基础设施：`docker compose up -d`
4. 起后端：`cd backend && uv sync && uv run alembic upgrade head && uv run python -m scripts.seed && uv run uvicorn app.main:app --reload --port 8000`
5. 起前端：`cd frontend && pnpm i && pnpm dev` → http://localhost:5173（演示账号 demo / Demo123456）

## 文档

- 设计文档：`docs/设计/`
- 实施计划：`docs/superpowers/plans/`
