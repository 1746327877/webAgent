from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_declares_full_stack():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ("postgres:", "redis:", "backend:", "worker:", "frontend:"):
        assert f"\n  {service}" in text
    assert "host.docker.internal:host-gateway" in text
    assert "alembic upgrade head" in text and "scripts.seed_all" in text
    # 后端宿主端口可配置（默认 8000；部分 Windows 机器把 8000 划进保留段时会 bind 失败）
    assert "BACKEND_PORT:-8000" in text
    # 前端宿主端口可配置（默认 8090，避开常被 Steam 等占用的 8080）
    assert "FRONTEND_PORT:-8090" in text


def test_compose_declares_web_search_and_mineru():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    # 联网搜索 MCP 服务与可配置宿主端口（默认 3300，避开 Windows 保留段）
    assert "web-search:" in text
    assert "ghcr.io/aas-ee/open-web-search" in text
    assert "WEB_SEARCH_PORT" in text
    # MinerU 走宿主机服务，通过环境变量启用（留空则回退内置解析）
    assert "MINERU_API_URL" in text


def test_nginx_proxies_api_and_disables_buffering():
    text = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_buffering off" in text
    assert "location /api/" in text
    assert "location /v1/" in text
    assert "backend:8000" in text


def test_nginx_allows_large_uploads():
    text = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    # 后端文档 20MB / 图片 5MB，nginx 默认 1m 会在到达 FastAPI 前 413
    assert "client_max_body_size 25m;" in text


def test_dockerfiles_use_locked_installs():
    backend = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen" in backend
    assert "COPY alembic ./alembic" in backend
    assert "pnpm install --frozen-lockfile" in frontend
    assert "nginx" in frontend
