"""Generate the stripped-sections callout box with optional QR code."""

from __future__ import annotations

import base64
import io
import urllib.parse


def _article_url(title: str) -> str:
    slug = urllib.parse.quote(title.replace(" ", "_"))
    return f"https://en.wikipedia.org/wiki/{slug}"


def generate_qr_data_uri(url: str) -> str:
    """Generate a QR code as a base64 PNG data URI."""
    import qrcode

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def generate_callout_html(
    title: str,
    stripped_sections: list[str],
    include_qr: bool = True,
    qr_size_in: float = 0.75,
) -> str:
    """Build the HTML for the stripped-sections callout box."""
    if not stripped_sections:
        return ""

    url = _article_url(title)
    section_list = ", ".join(stripped_sections)

    qr_html = ""
    if include_qr:
        data_uri = generate_qr_data_uri(url)
        qr_html = (
            f'<img class="callout-qr" src="{data_uri}" '
            f'alt="QR code to {url}" '
            f'style="width: {qr_size_in}in; height: {qr_size_in}in;" />'
        )

    return f"""<div class="stripped-sections-callout">
  {qr_html}
  <p>Read the full article including {section_list} at
  <a href="{url}">{url}</a></p>
</div>
"""
