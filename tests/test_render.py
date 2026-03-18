"""Tests for PDF rendering and validation."""

from cc_wp_book.config import TrimSize, VolumeConfig
from cc_wp_book.render import render_article_html, render_pdf, validate_pdf


class TestRenderArticleHtml:
    def test_contains_title(self):
        html = render_article_html("Earth", "<p>Content</p>", [])
        assert "<h1" in html
        assert "Earth" in html

    def test_contains_body(self):
        html = render_article_html("Earth", "<p>Content here</p>", [])
        assert "Content here" in html

    def test_includes_callout_when_sections_stripped(self):
        html = render_article_html(
            "Earth", "<p>Body</p>", ["References"],
        )
        assert "stripped-sections-callout" in html
        assert "References" in html

    def test_no_callout_when_no_sections_stripped(self):
        html = render_article_html("Earth", "<p>Body</p>", [])
        assert "stripped-sections-callout" not in html

    def test_includes_lead_image(self):
        html = render_article_html(
            "Earth", "<p>Body</p>", [],
            lead_image_path="/tmp/earth.jpg",
        )
        assert "/tmp/earth.jpg" in html
        assert "lead-image" in html

    def test_applies_heading_font(self):
        from cc_wp_book.config import TypographyConfig
        typo = TypographyConfig(heading_font="Custom Heading")
        html = render_article_html(
            "Earth", "<p>Body</p>", [], typography=typo,
        )
        assert "Custom Heading" in html


class TestRenderPdf:
    def test_creates_pdf_file(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        render_pdf("<p>Hello world</p>", pdf)
        assert pdf.exists()
        assert pdf.stat().st_size > 0

    def test_applies_trim_size(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        vol = VolumeConfig(
            trim_size=TrimSize(width_in=6.0, height_in=9.0)
        )
        render_pdf("<p>Hello</p>", pdf, vol)
        issues = validate_pdf(pdf, vol)
        assert issues == []


class TestValidatePdf:
    def test_missing_file(self, tmp_path):
        issues = validate_pdf(tmp_path / "nope.pdf")
        assert any("not found" in i for i in issues)

    def test_empty_file(self, tmp_path):
        pdf = tmp_path / "empty.pdf"
        pdf.write_bytes(b"")
        issues = validate_pdf(pdf)
        assert any("empty" in i for i in issues)

    def test_valid_pdf(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        render_pdf("<p>Valid content</p>", pdf)
        issues = validate_pdf(pdf)
        assert issues == []

    def test_page_size_check(self, tmp_path):
        pdf = tmp_path / "test.pdf"
        render_pdf(
            "<p>Content</p>", pdf,
            VolumeConfig(trim_size=TrimSize(width_in=6.0, height_in=9.0)),
        )
        wrong_size = VolumeConfig(
            trim_size=TrimSize(width_in=8.5, height_in=11.0)
        )
        issues = validate_pdf(pdf, wrong_size)
        assert any("Page size" in i for i in issues)
