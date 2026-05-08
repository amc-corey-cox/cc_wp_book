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


def _grouped_ref_tag_ids(parsed) -> set[int]:
    """Collect id() values of <ref> tags that belong to a non-default group.

    Includes:
    - Refs with explicit `group="..."` attribute.
    - Refs declared inside `{{reflist|group=...|refs=...}}` templates.

    Note: `{{refn|group=n|...}}` templates create their own refs that we
    don't pick up via `<ref>` tag walking — those notes are left in their
    original Wikipedia rendering since we skip the Notes <ol> wholesale.
    """
    grouped: set[int] = set()
    for template in parsed.filter_templates():
        name = str(template.name).strip().lower()
        if not name.startswith("reflist"):
            continue
        if not template.has("group"):
            continue
        if not template.has("refs"):
            continue
        for ref_tag in template.get("refs").value.filter_tags():
            if str(ref_tag.tag).lower() == "ref":
                grouped.add(id(ref_tag))
    return grouped


@dataclass
class _ExtractedCitations:
    by_name: dict[str, Citation]
    anonymous: list[Citation]  # in document order


def _extract_default_group_citations(wikitext: str) -> _ExtractedCitations:
    """Walk wikitext for default-group refs only.

    Returns:
        by_name: {ref_name: Citation} for named default-group refs.
        anonymous: list of Citations for anonymous default-group refs in
                   the order they first appear in the document.

    Refs in non-default groups (explicit `group=` or inside grouped reflist
    templates) are skipped — their corresponding <li> entries live in the
    Notes <ol>, which we leave untouched in the HTML rewrite.
    """
    parsed = mwparserfromhell.parse(wikitext)
    grouped = _grouped_ref_tag_ids(parsed)

    # First, determine grouping per name (a name is grouped if ANY
    # occurrence has the group attribute or sits in a grouped reflist).
    name_grouped: dict[str, bool] = {}
    for tag in parsed.filter_tags():
        if str(tag.tag).lower() != "ref":
            continue
        if not tag.has("name"):
            continue
        name = str(tag.get("name").value).strip()
        if tag.has("group") or id(tag) in grouped:
            name_grouped[name] = True
        elif name not in name_grouped:
            name_grouped[name] = False

    by_name: dict[str, Citation] = {}
    anonymous: list[Citation] = []

    for tag in parsed.filter_tags():
        if str(tag.tag).lower() != "ref":
            continue
        if not tag.contents:
            continue

        if tag.has("name"):
            name = str(tag.get("name").value).strip()
            if name_grouped.get(name, False):
                continue
            if name in by_name:
                continue
            citation = _build_citation_from_tag(tag)
            if citation is not None:
                by_name[name] = citation
        else:
            tag_grouped = tag.has("group") or id(tag) in grouped
            if tag_grouped:
                continue
            citation = _build_citation_from_tag(tag)
            if citation is not None:
                anonymous.append(citation)

    return _ExtractedCitations(by_name=by_name, anonymous=anonymous)


def extract_citation_map(wikitext: str) -> dict[int, Citation]:
    """Backwards-compatible position-keyed view used by tests.

    Returns positions 1..N over the union of named and anonymous
    default-group citations, ordered named first then anonymous-by-document.
    Real HTML rewrite uses the by-name + by-anonymous-position lookup
    (`rewrite_references_inplace`), not this map.
    """
    extracted = _extract_default_group_citations(wikitext)
    out: dict[int, Citation] = {}
    n = 1
    for citation in extracted.by_name.values():
        out[n] = citation
        n += 1
    for citation in extracted.anonymous:
        out[n] = citation
        n += 1
    return out


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

_OL_PATTERN = re.compile(
    r'<ol class="references[^"]*"[^>]*>.*?</ol>',
    re.DOTALL,
)


def _name_from_li_id(id_value: str) -> Optional[str]:
    """Extract the ref-name from a cite_note id like `NAME-N`. Returns
    None for purely numeric (anonymous) IDs. Decodes HTML entity-escaped
    underscores."""
    decoded = id_value.replace("&#95;", "_")
    m = re.match(r"^(.+?)-\d+$", decoded)
    if m:
        return m.group(1)
    return None  # purely numeric → anonymous


def _heading_preceding(html: str, ol_start: int) -> str:
    """Return the text of the most recent <h2>/<h3> before ol_start, or ''."""
    preceding = html[:ol_start]
    h_matches = list(re.finditer(
        r'<h[2-3][^>]*>(.*?)</h[2-3]>', preceding, re.DOTALL,
    ))
    if not h_matches:
        return ""
    inner = h_matches[-1].group(1)
    return re.sub(r"<[^>]+>", "", inner).strip()


def _is_notes_ol(heading_text: str) -> bool:
    return heading_text.strip().lower() == "notes"


def rewrite_references_inplace(
    html: str, wikitext: str
) -> str:
    """Walk each <ol class="references"> in HTML and rewrite its <li>
    entries using our compact CS1 rendering, EXCEPT for the Notes <ol>
    which is left entirely untouched.

    Within each rewritten <ol>:
    - Named refs (li id `cite_note-NAME-N`) are matched to wikitext by NAME.
    - Anonymous refs (li id `cite_note-N`) are matched by their position in
      the default-group anonymous-ref sequence within this <ol>.
    - Same-source repeats render as shortened form (Author (Year), p. N.).
    """
    extracted = _extract_default_group_citations(wikitext)
    if not extracted.by_name and not extracted.anonymous:
        return html

    # Pre-render with same-source dedupe applied across the whole bibliography.
    # Walk in the order: named (sorted by first-seen — already preserved by
    # dict insertion order) then anonymous (in document order).
    all_in_order: list[Citation] = list(extracted.by_name.values()) + list(
        extracted.anonymous
    )
    rendered_full: dict[int, str] = render_citations(
        {i: c for i, c in enumerate(all_in_order)}
    )
    name_to_render = {
        name: rendered_full[i]
        for i, name in enumerate(extracted.by_name.keys())
    }
    anon_renders = [
        rendered_full[len(extracted.by_name) + i]
        for i in range(len(extracted.anonymous))
    ]

    def rewrite_one_ol(ol_html: str, anon_cursor: list[int]) -> str:
        def replace(match: re.Match) -> str:
            opening = match.group(1)
            id_value = match.group(2)
            closing = match.group(4)

            ref_name = _name_from_li_id(id_value)
            if ref_name is not None:
                rendered = name_to_render.get(ref_name)
                if rendered is None:
                    return match.group(0)
                return f"{opening}{rendered}{closing}"
            else:
                if anon_cursor[0] >= len(anon_renders):
                    return match.group(0)
                rendered = anon_renders[anon_cursor[0]]
                anon_cursor[0] += 1
                return f"{opening}{rendered}{closing}"

        return _LI_PATTERN.sub(replace, ol_html)

    anon_cursor = [0]
    out_parts: list[str] = []
    last_end = 0

    for ol_match in _OL_PATTERN.finditer(html):
        out_parts.append(html[last_end:ol_match.start()])
        heading = _heading_preceding(html, ol_match.start())
        if _is_notes_ol(heading):
            out_parts.append(ol_match.group(0))  # untouched
        else:
            out_parts.append(rewrite_one_ol(ol_match.group(0), anon_cursor))
        last_end = ol_match.end()
    out_parts.append(html[last_end:])
    return "".join(out_parts)
