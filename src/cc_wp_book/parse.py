"""Parse and strip sections from Wikipedia wikitext and rendered HTML."""

from __future__ import annotations

import re
from dataclasses import dataclass

import mwparserfromhell


@dataclass
class ParseResult:
    title: str
    cleaned_wikitext: str
    cleaned_html: str
    stripped_sections: list[str]
    kept_sections: list[str]


def strip_sections(
    wikitext: str,
    sections_to_strip: set[str],
    title: str = "",
    html: str = "",
) -> ParseResult:
    """Remove specified sections from wikitext and corresponding HTML.

    Strips top-level sections whose header text (case-insensitive) matches
    any entry in `sections_to_strip`. All sub-sections under a matched
    header are also removed.
    """
    parsed = mwparserfromhell.parse(wikitext)
    sections = parsed.get_sections(
        include_lead=True, include_headings=True
    )

    stripped: list[str] = []
    kept: list[str] = []
    output_parts: list[str] = []
    stripping_level: int | None = None

    for section in sections:
        headings = section.filter_headings()
        if not headings:
            output_parts.append(str(section))
            continue

        heading = headings[0]
        level = heading.level
        heading_text = heading.title.strip_code().strip()
        normalized = heading_text.lower()

        if stripping_level is not None:
            if level > stripping_level:
                stripped.append(heading_text)
                continue
            else:
                stripping_level = None

        if normalized in sections_to_strip:
            stripped.append(heading_text)
            stripping_level = level
            continue

        kept.append(heading_text)
        output_parts.append(str(section))

    cleaned_wikitext = "\n".join(output_parts)
    cleaned_html = ""
    if html:
        cleaned_html = strip_sections_from_html(html, sections_to_strip)
        cleaned_html = reposition_infobox(cleaned_html)
        # Strip <style> blocks — we provide our own print CSS
        cleaned_html = re.sub(
            r"<style[^>]*>.*?</style>", "", cleaned_html, flags=re.DOTALL
        )
        # Fix protocol-relative URLs for offline rendering
        cleaned_html = cleaned_html.replace('src="//', 'src="https://')
        cleaned_html = cleaned_html.replace('href="//', 'href="https://')

    return ParseResult(
        title=title,
        cleaned_wikitext=cleaned_wikitext,
        cleaned_html=cleaned_html,
        stripped_sections=stripped,
        kept_sections=kept,
    )


def _extract_table(html: str, start: int) -> str | None:
    """Extract a complete <table>...</table> from `start`, handling nesting."""
    depth = 0
    i = start
    while i < len(html):
        open_match = re.search(r"<table\b", html[i:], re.IGNORECASE)
        close_match = re.search(r"</table>", html[i:], re.IGNORECASE)
        if close_match is None:
            return None
        if open_match and open_match.start() < close_match.start():
            depth += 1
            i += open_match.start() + 6
        else:
            depth -= 1
            end = i + close_match.end()
            if depth == 0:
                return html[start:end]
            i = end
    return None


def reposition_infobox(html: str) -> str:
    """Move the infobox from the top of the article to after the lead paragraphs.

    Wikipedia's HTML puts the infobox table before the lead text.
    For print, we move it to just before the first <h2>, so readers
    get the introductory paragraphs first, then the fact sheet.

    The infobox image row is stripped (the lead image is rendered
    separately as a full-width hero) and the caption row is removed
    since the title is already in the article header.
    """
    infobox_match = re.search(
        r'<table\b[^>]*class="[^"]*\binfobox\b', html, re.IGNORECASE
    )
    if not infobox_match:
        return html

    extracted_html = _extract_table(html, infobox_match.start())
    if not extracted_html:
        return html

    # Strip the image row and caption from the infobox
    stripped_html = _strip_infobox_image(extracted_html)

    # Remove infobox from original position — slice with the *original* length
    html_without = (
        html[:infobox_match.start()] +
        html[infobox_match.start() + len(extracted_html):]
    )

    # Find first <h2> — the boundary between lead and body sections
    first_h2 = re.search(r"<h2[\s>]", html_without)
    if not first_h2:
        return html_without + _wrap_infobox(stripped_html)

    insert_pos = first_h2.start()
    return (
        html_without[:insert_pos] +
        _wrap_infobox(stripped_html) +
        html_without[insert_pos:]
    )


def _strip_infobox_image(infobox_html: str) -> str:
    """Remove the image row and caption from an infobox table.

    These are redundant in print since the lead image is rendered
    as a full-width hero above the article.
    """
    # Remove caption element (contains the article title)
    infobox_html = re.sub(
        r"<caption[^>]*>.*?</caption>", "", infobox_html, flags=re.DOTALL
    )
    # Remove rows with class="infobox-image"
    infobox_html = re.sub(
        r"<tr>\s*<td[^>]*class=\"[^\"]*infobox-image[^\"]*\"[^>]*>.*?</td>\s*</tr>",
        "", infobox_html, flags=re.DOTALL,
    )
    return infobox_html


def _wrap_infobox(infobox_html: str) -> str:
    """Wrap the infobox in a print-friendly container."""
    return (
        '<div class="infobox-print-wrapper">'
        f'{infobox_html}'
        '</div>'
    )


def strip_sections_from_html(
    html: str, sections_to_strip: set[str]
) -> str:
    """Remove sections from Wikipedia's rendered HTML by heading text.

    Wikipedia's API returns HTML where sections are delimited by
    <h2>, <h3>, etc. tags containing <span class="mw-headline">.
    We split on these boundaries and filter out matched sections
    and their sub-sections.
    """
    heading_pattern = re.compile(
        r"<h(\d)\b[^>]*>.*?</h\1>", re.DOTALL
    )
    headline_text_pattern = re.compile(
        r'class="mw-headline"[^>]*>([^<]+)<'
    )

    parts: list[dict] = []
    last_end = 0

    for match in heading_pattern.finditer(html):
        if match.start() > last_end:
            parts.append({
                "type": "content",
                "text": html[last_end:match.start()],
            })
        text_match = headline_text_pattern.search(match.group())
        heading_text = text_match.group(1).strip() if text_match else ""
        level = int(match.group(1))
        parts.append({
            "type": "heading",
            "level": level,
            "name": heading_text,
            "text": match.group(),
        })
        last_end = match.end()

    if last_end < len(html):
        parts.append({"type": "content", "text": html[last_end:]})

    output: list[str] = []
    stripping_level: int | None = None

    for part in parts:
        if part["type"] == "heading":
            level = part["level"]
            normalized = part["name"].lower()

            if stripping_level is not None:
                if level > stripping_level:
                    continue
                else:
                    stripping_level = None

            if normalized in sections_to_strip:
                stripping_level = level
                continue

        if stripping_level is not None:
            continue

        output.append(part["text"])

    return "".join(output)
