from app.ai.rag import document_parser
from app.ai.rag.mineru_client import MinerUError
from app.core.config import settings


def test_pdf_uses_mineru_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")
    monkeypatch.setattr(
        document_parser.mineru_client, "parse_markdown", lambda path, file_type: "# MD"
    )
    assert document_parser.extract_pages(tmp_path / "a.pdf", "pdf") == [(None, "# MD")]


def test_falls_back_when_mineru_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")

    def boom(path, file_type):
        raise MinerUError("service down")

    monkeypatch.setattr(document_parser.mineru_client, "parse_markdown", boom)
    from app.ai.rag import parsers

    monkeypatch.setattr(parsers, "extract_text", lambda path, file_type: [(1, "fallback")])
    assert document_parser.extract_pages(tmp_path / "a.pdf", "pdf") == [(1, "fallback")]


def test_falls_back_when_mineru_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")
    monkeypatch.setattr(
        document_parser.mineru_client, "parse_markdown", lambda path, file_type: "   "
    )
    from app.ai.rag import parsers

    monkeypatch.setattr(parsers, "extract_text", lambda path, file_type: [(None, "builtin")])
    assert document_parser.extract_pages(tmp_path / "a.pdf", "pdf") == [(None, "builtin")]


def test_disabled_skips_mineru(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "")

    def should_not_call(path, file_type):
        raise AssertionError("MinerU should not be called when disabled")

    monkeypatch.setattr(document_parser.mineru_client, "parse_markdown", should_not_call)
    from app.ai.rag import parsers

    monkeypatch.setattr(parsers, "extract_text", lambda path, file_type: [(None, "builtin")])
    assert document_parser.extract_pages(tmp_path / "a.docx", "docx") == [(None, "builtin")]


def test_markdown_type_never_uses_mineru(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mineru_api_url", "http://mineru.test:8001")

    def should_not_call(path, file_type):
        raise AssertionError("MinerU only handles pdf/docx")

    monkeypatch.setattr(document_parser.mineru_client, "parse_markdown", should_not_call)
    path = tmp_path / "note.md"
    path.write_text("# note", encoding="utf-8")
    assert document_parser.extract_pages(path, "md") == [(None, "# note")]
