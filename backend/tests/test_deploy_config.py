from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_declares_full_stack():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for service in ("postgres:", "redis:", "backend:", "worker:", "frontend:"):
        assert f"\n  {service}" in text
    assert "host.docker.internal:host-gateway" in text
    assert "alembic upgrade head" in text and "scripts.seed_all" in text
    assert "8080:80" in text


def test_nginx_proxies_api_and_disables_buffering():
    text = (ROOT / "frontend" / "nginx.conf").read_text(encoding="utf-8")
    assert "proxy_buffering off" in text
    assert "location /api/" in text
    assert "location /v1/" in text
    assert "backend:8000" in text


def test_dockerfiles_use_locked_installs():
    backend = (ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
    frontend = (ROOT / "frontend" / "Dockerfile").read_text(encoding="utf-8")
    assert "uv sync --frozen" in backend
    assert "COPY alembic ./alembic" in backend
    assert "pnpm install --frozen-lockfile" in frontend
    assert "nginx" in frontend
