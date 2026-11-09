"""pdf_render — markdown → PDF assembly with WeasyPrint mocked at the boundary.

The pure parts (escaping, data-URI building, figure HTML, SSRF-blocking url
fetcher, markdown → HTML) run for real; only the WeasyPrint ``HTML`` render
itself is stubbed so no font/layout engine is exercised.
"""
from __future__ import annotations

import base64

import pytest

import services.pdf_render as pr


class FakeHTML:
    """Captures the assembled document; write_pdf returns marker bytes."""

    last_doc = None
    last_url_fetcher = None

    def __init__(self, string="", **kwargs):
        FakeHTML.last_doc = string
        FakeHTML.last_url_fetcher = kwargs.get("url_fetcher")

    def write_pdf(self, target=None):
        payload = b"%PDF-fake"
        if target is not None:
            target.write(payload)
            target.seek(0)
            return target
        return payload


@pytest.fixture()
def fake_html(monkeypatch):
    FakeHTML.last_doc = None
    FakeHTML.last_url_fetcher = None
    monkeypatch.setattr(pr, "HTML", FakeHTML)
    return FakeHTML


# --- pure helpers ------------------------------------------------------------

def test_escape():
    assert pr._escape(None) == ""
    assert pr._escape("a<b>&c") == "a&lt;b&gt;&amp;c"


def test_image_data_uri_valid_content_type():
    uri = pr.image_data_uri(b"pngbytes", "image/png")
    assert uri == "data:image/png;base64," + base64.b64encode(b"pngbytes").decode()


@pytest.mark.parametrize("bad", [
    "text/html", "image/png; x", "image/svg+xml onload=alert(1)",
    "", "image/" + "a" * 60, "notanimage",
])
def test_image_data_uri_rejects_bad_content_type(bad):
    # Anything that is not a plain image/* type falls back to image/png and
    # cannot break out of the src attribute.
    assert pr.image_data_uri(b"x", bad).startswith("data:image/png;base64,")


def test_figures_html_empty():
    assert pr._figures_html(None) == ""
    assert pr._figures_html([]) == ""
    # Figures without a data_uri are skipped entirely → no section emitted.
    assert pr._figures_html([{"caption": "no image"}]) == ""


def test_figures_html_renders_numbered_figures_with_escaped_caption():
    html = pr._figures_html([
        {"data_uri": "data:image/png;base64,AAA", "caption": "XSS <script>alert(1)</script>"},
        {"data_uri": "data:image/png;base64,BBB", "caption": ""},
    ])
    assert "<h2>Evidence — Screenshots</h2>" in html
    assert "Figure 1 — XSS &lt;script&gt;" in html
    assert "<script>" not in html
    assert "Figure 2" in html  # caption-less figure still numbered


def test_blocked_url_fetcher_rejects_remote_schemes():
    for url in ("http://evil.example/x.png", "https://evil.example/x.png",
                "file:///etc/passwd", "ftp://x/y"):
        with pytest.raises(ValueError, match="blocked non-data resource"):
            pr._blocked_url_fetcher(url)


def test_blocked_url_fetcher_delegates_data_uris(monkeypatch):
    seen = {}

    def fake_default(url):
        seen["url"] = url
        return {"content": b"x"}

    monkeypatch.setattr(pr, "default_url_fetcher", fake_default)
    pr._blocked_url_fetcher("data:image/png;base64,AAA")
    assert seen["url"] == "data:image/png;base64,AAA"


# --- markdown_to_pdf (render mocked) -----------------------------------------

def test_markdown_to_pdf_assembles_document(fake_html):
    out = pr.markdown_to_pdf("# Heading\n\n| a | b |\n|---|---|\n| 1 | 2 |",
                             title="SQLi <report>")
    assert out == b"%PDF-fake"
    doc = fake_html.last_doc
    assert fake_html.last_url_fetcher is pr._blocked_url_fetcher
    assert "<title>SQLi &lt;report&gt;</title>" in doc
    assert "<h1>Heading</h1>" in doc
    assert "<table>" in doc  # tables extension active
    assert "aida-footer" in doc


def test_markdown_to_pdf_empty_input_still_renders_footer(fake_html):
    pr.markdown_to_pdf("", title="")
    assert "<title>Vulnerability Report</title>" in fake_html.last_doc
    assert "Evidence — Screenshots" not in fake_html.last_doc


def test_markdown_to_pdf_appends_figures_section(fake_html):
    pr.markdown_to_pdf("body", figures=[{"data_uri": "data:image/png;base64,QQ==",
                                         "caption": "proof"}])
    doc = fake_html.last_doc
    assert "Evidence — Screenshots" in doc
    assert "data:image/png;base64,QQ==" in doc
    # Body comes before the evidence appendix.
    assert doc.index("body") < doc.index("Evidence — Screenshots")
