import io
import zipfile
from pathlib import Path

import httpx
import pytest
import respx

from app.ai.rag import mineru_client
from app.core.config import settings

URL = "http://mineru.test:8001/file_parse"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")


def _fake_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "doc.pdf"
    path.write_bytes(b"%PDF-1.4 fake")
    return path


@respx.mock
def test_parse_markdown_from_nested_json(tmp_path, enabled):
    respx.post(URL).mock(
        return_value=httpx.Response(
            200, json={"results": {"doc.pdf": {"md_content": "# 标题\n\n正文"}}}
        )
    )
    assert mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf") == "# 标题\n\n正文"


@respx.mock
def test_parse_markdown_from_zip(tmp_path, enabled):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("doc/auto/doc.md", "# Zip 内容")
    respx.post(URL).mock(
        return_value=httpx.Response(
            200, content=buf.getvalue(), headers={"content-type": "application/zip"}
        )
    )
    assert "Zip 内容" in mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")


@respx.mock
def test_parse_markdown_from_real_response_shape(tmp_path, enabled):
    """实测结构：顶层还有 task_id/status 等字段，不能被误当正文。"""
    respx.post(URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "task_id": "b7b02505",
                "status": "completed",
                "backend": "pipeline",
                "error": None,
                "results": {"doc": {"md_content": "# 标题\n\n正文"}},
            },
        )
    )
    assert mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf") == "# 标题\n\n正文"


@respx.mock
def test_parse_markdown_failed_status(tmp_path, enabled):
    respx.post(URL).mock(
        return_value=httpx.Response(
            409,
            json={"status": "failed", "error": "CUDA is not available."},
        )
    )
    with pytest.raises(mineru_client.MinerUError, match="CUDA is not available"):
        mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")


@respx.mock
def test_sends_pipeline_backend(tmp_path, enabled):
    route = respx.post(URL).mock(
        return_value=httpx.Response(200, json={"results": {"doc": {"md_content": "# ok"}}})
    )
    mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")
    body = route.calls[0].request.content.decode("utf-8", errors="ignore")
    assert "pipeline" in body


@respx.mock
def test_parse_markdown_http_error(tmp_path, enabled):
    respx.post(URL).mock(return_value=httpx.Response(500, text="boom"))
    with pytest.raises(mineru_client.MinerUError, match="HTTP 500"):
        mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")


@respx.mock
def test_parse_markdown_connect_error(tmp_path, enabled):
    respx.post(URL).mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(mineru_client.MinerUError, match="连接 MinerU 失败"):
        mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")


def test_parse_markdown_requires_config(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "")
    with pytest.raises(mineru_client.MinerUError, match="MINERU_API_URL"):
        mineru_client.parse_markdown(_fake_pdf(tmp_path), "pdf")
