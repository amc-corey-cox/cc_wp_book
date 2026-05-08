"""Compact CS1-style citation rendering for print.

Wikipedia uses Citation Style 1 (CS1) via {{cite book}}, {{cite journal}}, etc.
For print, we extract the structured fields from the wikitext templates and
re-render a compact, CS1-conformant subset. URLs, DOIs, ISBNs, archive links,
and access dates are dropped — the article-level QR/Wikipedia pointer is the
digital companion that closes that gap.

Approach: in-place transform. Wikipedia's renderer has already deduplicated
refs and assigned them positions in the rendered <ol class="references">.
We walk those <li> entries and replace the content of each with our compact
rendering, looking up the corresponding wikitext template by position.

Refs declared inside {{reflist|refs=...}} (Wikipedia's pattern for
explanatory-note groups) are not picked up by our top-level walk, so those
<li>s are left untouched — Notes-style footnotes keep their original
rendering until they're addressed in their own pass.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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
    container: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None  # "p. 49" or "pp. 13114-13119" form
    raw_html: Optional[str] = None


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
    """Return the first non-empty value among the named params.

    Strips wikitext markup ([[link]], ''italic'', nested templates) so the
    returned string is plain text suitable for our own re-formatting.
    """
    for name in names:
        if template.has(name):
            wikicode = template.get(name).value
            value = wikicode.strip_code().strip()
            value = re.sub(r"\s+", " ", value)
            if value:
                return value
    return None


def _initials(first: str) -> str:
    return " ".join(f"{p[0]}." for p in re.split(r"\s+", first) if p)


def _format_authors(template) -> Optional[str]:
    last1 = _get_param(template, "last1", "last")
    first1 = _get_param(template, "first1", "first")
    if not last1:
        author1 = _get_param(template, "author1", "author")
        if author1:
            has_more = template.has("last2") or template.has("author2")
            return author1 + (" et al." if has_more else "")
        return None

    initials = " " + _initials(first1) if first1 else ""
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
    initials = " " + _initials(first) if first else ""
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


def _format_pages(template) -> Optional[str]:
    pages = _get_param(template, "pages")
    if pages:
        return f"pp. {pages}"
    page = _get_param(template, "page")
    if page:
        return f"p. {page}"
    return None


def _build_citation_from_template(template) -> Optional[Citation]:
    name = str(template.name).strip().lower()
    citation_type = _CITE_TYPES.get(name)
    if citation_type is None:
        return None

    c = Citation(type=citation_type)
    c.author = _format_authors(template) or _format_editors(template)
    c.year = _format_year(template)
    c.title = _get_param(template, "title")
    c.chapter = _get_param(template, "chapter")

    if citation_type == "book":
        c.container = _get_param(template, "publisher")
        c.pages = _format_pages(template)
    elif citation_type == "journal":
        c.container = _get_param(template, "journal", "periodical")
        c.volume = _get_param(template, "volume")
        c.issue = _get_param(template, "issue", "number")
        c.pages = _format_pages(template)
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
    text = node.strip_code() if hasattr(node, "strip_code") else str(node)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_citation_from_tag(tag) -> Optional[Citation]:
    """Pick the first cite template inside a <ref>'s contents, or fall back
    to free-text rendering. Returns None if the result would be empty."""
    templates = tag.contents.filter_templates(recursive=False)
    cite_template = next(
        (t for t in templates if str(t.name).strip().lower() in _CITE_TYPES),
        None,
    )
    if cite_template is not None:
        c = _build_citation_from_template(cite_template)
        if c is not None and (c.title or c.author or c.container):
            return c

    raw = _free_text_html(tag.contents)
    if not raw:
        return None
    return Citation(type="free", raw_html=raw)


def extract_citation_map(wikitext: str) -> dict[int, Citation]:
    """Build {visible_position: Citation} aligned with Wikipedia's renderer.

    Walks <ref> tags recursively so refs inside templates and tables are
    picked up (matches Wikipedia's renderer behavior).

    Dedupe matches Wikipedia: named refs first occurrence wins; subsequent
    occurrences (self-closing reuse or repeated content) share the position.
    Anonymous refs are NOT deduped by content — each anonymous <ref> tag is
    its own entry, even if textually identical, since they often differ in
    page= or other params (Wikipedia treats them as distinct).
    """
    parsed = mwparserfromhell.parse(wikitext)
    name_positions: dict[str, int] = {}
    citations: dict[int, Citation] = {}
    next_pos = 1

    for tag in parsed.filter_tags():
        if str(tag.tag).lower() != "ref":
            continue
        if not tag.contents:
            continue

        # Skip refs in non-default groups (e.g., group="n" for Notes).
        # Those have their own <ol class="references"> rendered separately
        # and are intentionally left untouched here.
        if tag.has("group"):
            continue

        if tag.has("name"):
            name = str(tag.get("name").value).strip()
            if name in name_positions:
                continue
            name_positions[name] = next_pos

        citation = _build_citation_from_tag(tag)
        if citation is None:
            continue
        citations[next_pos] = citation
        next_pos += 1

    return citations


def _terminate(s: str) -> str:
    return s if s.endswith(".") else s + "."


def _essence_key(c: Citation):
    """Identity key for a citation (excludes pages and raw_html).

    Two citations sharing this key are the same source — they may differ
    only in which page is being cited. Returns None if the citation isn't
    a candidate for dedupe (free text, missing fields).
    """
    if c.type == "free":
        return None
    if not (c.author or c.title):
        return None
    return (c.type, c.author, c.year, c.title, c.container, c.volume, c.issue, c.chapter)


def _short_author(author: str) -> str:
    """Reduce 'Last, F.' / 'Last, F. et al.' → 'Last' / 'Last et al.'"""
    is_etal = "et al" in author
    head = author.split(",")[0] if "," in author else author.split()[0]
    head = head.rstrip(".")
    return f"{head} et al." if is_etal else head


def format_shortened(c: Citation) -> str:
    """Short academic-style backreference: 'Author (Year), p. N.'

    Used for the 2nd and later occurrences of the same source in the
    bibliography — saves roughly 60-70% per repeat versus the full form.
    """
    parts: list[str] = []
    if c.author:
        parts.append(_short_author(c.author))
    if c.year:
        parts.append(f"({c.year})")
    base = " ".join(parts) or (c.title or "Cited source")
    if c.pages:
        return f"{base}, {c.pages}."
    return base + "."


def render_citations(citations: dict[int, Citation]) -> dict[int, str]:
    """Render every citation, using shortened form for repeat occurrences
    of the same source. Walks positions in order so the first occurrence
    gets the full citation and subsequent ones get the short form.
    """
    rendered: dict[int, str] = {}
    seen: dict[tuple, int] = {}

    for pos in sorted(citations):
        c = citations[pos]
        key = _essence_key(c)
        if key is not None and key in seen:
            rendered[pos] = format_shortened(c)
        else:
            if key is not None:
                seen[key] = pos
            rendered[pos] = format_compact(c)

    return rendered


def format_compact(c: Citation) -> str:
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

    if c.pages:
        parts.append(f"{c.pages}.")

    if not c.author and c.year:
        parts.append(f"({c.year}).")

    return " ".join(parts)


_LI_PATTERN = re.compile(
    r'(<li id="cite(?:_|&#95;)note-([^"]+)"[^>]*>)(.*?)(</li>)',
    re.DOTALL | re.IGNORECASE,
)


def _position_from_li_id(id_value: str) -> Optional[int]:
    """Extract trailing position number from a cite_note id.

    Both `cite_note-NAME-N` and `cite_note-N` end with the visible
    list-position number. We just match the trailing digits.
    """
    m = re.search(r"(\d+)$", id_value)
    return int(m.group(1)) if m else None


def rewrite_references_inplace(
    html: str, citations: dict[int, Citation]
) -> str:
    """For each <li id="cite_note-..."> in HTML, replace its inner content
    with our compact rendering if we have a Citation for that position.
    Otherwise leave the <li> unchanged.

    Repeat occurrences of the same source render in shortened form
    ('Rohli et al. (2018), p. 32.') to save space.
    """
    if not citations:
        return html

    rendered = render_citations(citations)

    def replace(match: re.Match) -> str:
        opening = match.group(1)
        id_value = match.group(2)
        closing = match.group(4)

        position = _position_from_li_id(id_value)
        if position is None or position not in rendered:
            return match.group(0)

        return f"{opening}{rendered[position]}{closing}"

    return _LI_PATTERN.sub(replace, html)
