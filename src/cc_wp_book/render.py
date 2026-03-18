"""Render articles to print-ready PDF via WeasyPrint."""

from __future__ import annotations

import logging
from pathlib import Path

from cc_wp_book.callout import generate_callout_html
from cc_wp_book.config import CalloutConfig, TypographyConfig, VolumeConfig

logger = logging.getLogger(__name__)

STYLES_DIR = Path(__file__).resolve().parent.parent.parent / "styles"


def _load_stylesheet() -> str:
    css_path = STYLES_DIR / "print.css"
    if css_path.exists():
        return css_path.read_text()
    return ""


def render_article_html(
    title: str,
    body_html: str,
    stripped_sections: list[str],
    lead_image_path: str | None = None,
    callout_config: CalloutConfig | None = None,
    typography: TypographyConfig | None = None,
) -> str:
    """Wrap API-rendered HTML in the article page template with callout."""
    cfg = callout_config or CalloutConfig()
    typo = typography or TypographyConfig()

    callout_html = ""
    if cfg.enabled and stripped_sections:
        callout_html = generate_callout_html(
            title=title,
            stripped_sections=stripped_sections,
            include_qr=cfg.qr_code,
            qr_size_in=cfg.qr_size_in,
        )

    lead_image_tag = ""
    if lead_image_path:
        lead_image_tag = (
            f'<div class="lead-image">'
            f'<img src="{lead_image_path}" alt="{title}" />'
            f"</div>"
        )

    font_family = f"'{typo.body_font}', serif"
    heading_family = f"'{typo.heading_font}', sans-serif"
    font_size = f"{typo.body_size_pt}pt"
    line_h = str(typo.line_height)

    return f"""<article class="wiki-article">
  <header class="article-header">
    {lead_image_tag}
    <h1 style="font-family: {heading_family};">{title}</h1>
  </header>
  <div class="article-body"
       style="font-family: {font_family};
              font-size: {font_size};
              line-height: {line_h};">
    {body_html}
  </div>
  {callout_html}
</article>
"""


def render_pdf(
    html_content: str,
    output_path: str | Path,
    volume_config: VolumeConfig | None = None,
) -> Path:
    """Render an HTML string to a PDF file."""
    from weasyprint import CSS, HTML

    vol = volume_config or VolumeConfig()
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width_pt = vol.trim_size.width_in * 72
    height_pt = vol.trim_size.height_in * 72
    bleed_pt = vol.bleed_in * 72

    page_css = f"""
    @page {{
        size: {width_pt}pt {height_pt}pt;
        margin: 0.75in 0.625in;
        bleed: {bleed_pt}pt;
        @bottom-center {{
            content: counter(page);
            font-size: 9pt;
        }}
    }}
    """

    stylesheet_text = _load_stylesheet()
    full_doc = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8" /></head>
<body>
{html_content}
</body>
</html>"""

    html = HTML(string=full_doc)
    css_objects = [CSS(string=page_css)]
    if stylesheet_text:
        css_objects.append(CSS(string=stylesheet_text))

    html.write_pdf(str(output_path), stylesheets=css_objects)
    logger.info("Rendered PDF: %s", output_path)
    return output_path


def validate_pdf(
    pdf_path: str | Path,
    volume_config: VolumeConfig | None = None,
) -> list[str]:
    """Validate a PDF against print specs. Returns list of issues."""
    from pypdf import PdfReader

    pdf_path = Path(pdf_path)
    issues: list[str] = []

    if not pdf_path.exists():
        issues.append(f"PDF not found: {pdf_path}")
        return issues

    if pdf_path.stat().st_size == 0:
        issues.append("PDF is empty (0 bytes)")
        return issues

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as exc:
        issues.append(f"PDF is malformed: {exc}")
        return issues

    if len(reader.pages) == 0:
        issues.append("PDF has 0 pages")
        return issues

    if volume_config:
        bleed = volume_config.bleed_in * 72
        expected_w = round(volume_config.trim_size.width_in * 72 + 2 * bleed, 1)
        expected_h = round(volume_config.trim_size.height_in * 72 + 2 * bleed, 1)
        page = reader.pages[0]
        media = page.mediabox
        actual_w = round(float(media.width), 1)
        actual_h = round(float(media.height), 1)
        if abs(actual_w - expected_w) > 1 or abs(actual_h - expected_h) > 1:
            issues.append(
                f"Page size {actual_w}x{actual_h}pt, "
                f"expected {expected_w}x{expected_h}pt "
                f"(trim + bleed)"
            )

    return issues
