"""Compact CS1-style citation rendering for print.

Wikipedia uses Citation Style 1 (CS1) via {{cite book}}, {{cite journal}}, etc.
For print, we extract the structured fields from wikitext templates and render
a compact, CS1-conformant subset. URLs, DOIs, ISBNs, archive links, and access
dates are dropped — the article-level QR/Wikipedia pointer is the digital
companion that closes that gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import mwparserfromhell


@dataclass
class Citation:
    type: str = "free"
    author: Optional[str] = None
    editor: Optional[str] = None
    year: Optional[str] = None
    title: Optional[str] = None
    chapter: Optional[str] = None
    container: Optional[str] = None  # journal | website | newspaper | encyclopedia | publisher
    volume: Optional[str] = None
    issue: Optional[str] = None
    raw_html: Optional[str] = None  # for free-text refs, preserved verbatim


_CITE_TYPES = {
    "cite book": "book",
    "cite journal": "journal",
    "cite web": "web",
    "cite news": "news",
    "cite encyclopedia": "encyclopedia",
    "cite dictionary": "encyclopedia",
    "cite conference": "conference",
}

_STANDALONE_TITLE_TYPES = {"book"}


def _get_param(template, *names: str) -> Optional[str]:
    """Return the first non-empty value among the named params."""
    for name in names:
        if template.has(name):
            value = str(template.get(name).value).strip()
            value = re.sub(r"\s+", " ", value)
            if value:
                return value
    return None


def _format_authors(template) -> Optional[str]:
    """CS1-style author rendering: 'Last, F.' or 'Last, F. et al.' if multiple."""
    last1 = _get_param(template, "last1", "last")
    first1 = _get_param(template, "first1", "first")
    if not last1:
        author1 = _get_param(template, "author1", "author")
        if author1:
            return author1 + (" et al." if template.has("last2") or template.has("author2") else "")
        return None

    initials = ""
    if first1:
        initials = " " + " ".join(
            f"{p[0]}." for p in re.split(r"\s+", first1) if p
        )
    has_more = (
        template.has("last2") or template.has("author2")
        or _get_param(template, "display-authors") == "etal"
    )
    return f"{last1},{initials}" + (" et al." if has_more else "")


def _format_editors(template) -> Optional[str]:
    last = _get_param(template, "editor-last", "editor1-last", "editor")
    first = _get_param(template, "editor-first", "editor1-first")
    if not last:
        return None
    initials = ""
    if first:
        initials = " " + " ".join(
            f"{p[0]}." for p in re.split(r"\s+", first) if p
        )
    return f"{last},{initials} (ed.)"


def _format_year(template) -> Optional[str]:
    year = _get_param(template, "year")
    if year:
        m = re.search(r"\d{4}", year)
        return m.group() if m else None
    date = _get_param(template, "date", "publication-date")
    if date:
        m = re.search(r"\d{4}", date)
        return m.group() if m else None
    return None


def _build_citation_from_template(template) -> Optional[Citation]:
    name = str(template.name).strip().lower()
    citation_type = _CITE_TYPES.get(name)
    if citation_type is None:
        return None

    c = Citation(type=citation_type)
    c.author = _format_authors(template) or _format_editors(template)
    if c.author is None and (ed := _format_editors(template)):
        c.editor = ed
    c.year = _format_year(template)
    c.title = _get_param(template, "title")
    c.chapter = _get_param(template, "chapter")

    if citation_type == "book":
        c.container = _get_param(template, "publisher")
    elif citation_type == "journal":
        c.container = _get_param(template, "journal", "periodical")
        c.volume = _get_param(template, "volume")
        c.issue = _get_param(template, "issue", "number")
    elif citation_type == "web":
        c.container = _get_param(template, "website", "work", "publisher")
    elif citation_type == "news":
        c.container = _get_param(template, "newspaper", "work", "publisher")
    elif citation_type == "encyclopedia":
        c.container = _get_param(template, "encyclopedia", "work", "publisher")
    elif citation_type == "conference":
        c.container = _get_param(template, "conference", "book-title", "work")

    return c


def _free_text_html(node) -> str:
    """Render a non-cite-template <ref> body as plain text, stripped of cruft.

    `node` is an mwparserfromhell Wikicode object. `strip_code()` removes
    wikitext markup ([[links]], ''italic'', templates, etc.) leaving readable
    plain text. We then collapse whitespace.
    """
    text = node.strip_code() if hasattr(node, "strip_code") else str(node)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_citations(wikitext: str) -> list[Citation]:
    """Walk wikitext <ref> tags in document order; return one Citation per
    *unique* ref (named refs deduped on first content occurrence; anonymous
    refs always counted; <ref name="X" /> reuses skipped).

    Order matches the rendered <ol class="references"> ordering.
    """
    code = mwparserfromhell.parse(wikitext)
    citations: list[Citation] = []
    seen_names: set[str] = set()

    for tag in code.filter_tags():
        if str(tag.tag).lower() != "ref":
            continue

        name_attr = tag.get("name") if tag.has("name") else None
        ref_name = str(name_attr.value).strip() if name_attr else None

        if not tag.contents:
            continue  # self-closing reuse like <ref name="X" />

        if ref_name is not None:
            if ref_name in seen_names:
                continue
            seen_names.add(ref_name)

        templates = tag.contents.filter_templates(recursive=False)
        cite_template = next(
            (t for t in templates if str(t.name).strip().lower() in _CITE_TYPES),
            None,
        )
        if cite_template is not None:
            citation = _build_citation_from_template(cite_template)
            if citation is not None:
                citations.append(citation)
                continue

        citations.append(Citation(type="free", raw_html=_free_text_html(tag.contents)))

    return citations


def _terminate(s: str) -> str:
    return s if s.endswith(".") else s + "."


def format_compact(c: Citation) -> str:
    """Render a Citation as compact CS1-conformant HTML."""
    if c.type == "free":
        return c.raw_html or ""

    parts: list[str] = []

    if c.author:
        parts.append(_terminate(c.author))
        if c.year:
            parts.append(f"({c.year}).")

    if c.chapter and c.title:
        parts.append(f'"{c.chapter}".')
        parts.append(f"In <i>{c.title}</i>.")
    elif c.title:
        if c.type in _STANDALONE_TITLE_TYPES:
            parts.append(f"<i>{c.title}</i>.")
        else:
            parts.append(f'"{c.title}".')

    if c.container:
        if c.type == "book":
            parts.append(f"{c.container}.")
        else:
            container_str = f"<i>{c.container}</i>"
            if c.type == "journal" and c.volume:
                container_str += f" {c.volume}"
                if c.issue:
                    container_str += f"({c.issue})"
            parts.append(container_str + ".")

    if not c.author and c.year:
        parts.append(f"({c.year}).")

    return " ".join(parts)


_REFERENCES_OL_PATTERN = re.compile(
    r'<ol class="references[^"]*"[^>]*>.*?</ol>',
    re.DOTALL,
)


def rewrite_references_section(html: str, citations: list[Citation]) -> str:
    """Replace each <ol class="references"> block with a compact rendering.

    The first block is replaced with our compact list of `citations`.
    Subsequent blocks (e.g., from a Notes section) are removed — we render
    a single consolidated bibliography.
    """
    if not citations:
        return _REFERENCES_OL_PATTERN.sub("", html)

    matches = list(_REFERENCES_OL_PATTERN.finditer(html))
    if not matches:
        return html

    items = "".join(
        f'<li id="cite_note-{i + 1}">{format_compact(c)}</li>'
        for i, c in enumerate(citations)
    )
    new_ol = f'<ol class="references">{items}</ol>'

    parts = [html[: matches[0].start()], new_ol]
    last_end = matches[0].end()
    for m in matches[1:]:
        parts.append(html[last_end : m.start()])
        last_end = m.end()
    parts.append(html[last_end:])
    return "".join(parts)
