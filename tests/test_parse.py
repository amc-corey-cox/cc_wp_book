"""Tests for section stripping logic."""

from cc_wp_book.parse import (
    reposition_infobox,
    strip_sections,
    strip_sections_from_html,
)

SAMPLE_WIKITEXT = """\
{{Infobox person
| name = Test Person
| born = 1900
}}
'''Test Person''' was a notable individual.

== Early life ==
Some content about early life.

=== Childhood ===
Details about childhood.

== Career ==
Career information here.

== See also ==
* [[Other article]]

== References ==
{{reflist}}

== External links ==
* [http://example.com Example]
"""

SAMPLE_HTML = """\
<p><b>Test Person</b> was a notable individual.</p>
<h2><span class="mw-headline" id="Early_life">Early life</span></h2>
<p>Some content about early life.</p>
<h3><span class="mw-headline" id="Childhood">Childhood</span></h3>
<p>Details about childhood.</p>
<h2><span class="mw-headline" id="Career">Career</span></h2>
<p>Career information here.</p>
<h2><span class="mw-headline" id="See_also">See also</span></h2>
<ul><li><a href="/wiki/Other">Other article</a></li></ul>
<h2><span class="mw-headline" id="References">References</span></h2>
<div class="reflist"></div>
<h2><span class="mw-headline" id="External_links">External links</span></h2>
<ul><li><a href="http://example.com">Example</a></li></ul>
"""

STRIP_SET = {"see also", "references", "external links"}


class TestStripSections:
    def test_strips_matching_sections(self):
        result = strip_sections(SAMPLE_WIKITEXT, STRIP_SET, title="Test Person")
        assert "See also" in result.stripped_sections
        assert "References" in result.stripped_sections
        assert "External links" in result.stripped_sections

    def test_keeps_non_matching_sections(self):
        result = strip_sections(SAMPLE_WIKITEXT, STRIP_SET, title="Test Person")
        assert "Early life" in result.kept_sections
        assert "Career" in result.kept_sections

    def test_preserves_content_of_kept_sections(self):
        result = strip_sections(SAMPLE_WIKITEXT, STRIP_SET)
        assert "Career information here" in result.cleaned_wikitext
        assert "Some content about early life" in result.cleaned_wikitext

    def test_removes_content_of_stripped_sections(self):
        result = strip_sections(SAMPLE_WIKITEXT, STRIP_SET)
        assert "Other article" not in result.cleaned_wikitext
        assert "reflist" not in result.cleaned_wikitext
        assert "example.com" not in result.cleaned_wikitext

    def test_case_insensitive_matching(self):
        wikitext = "Lead.\n\n== SEE ALSO ==\n* Link\n\n== Career ==\nStuff."
        result = strip_sections(wikitext, {"see also"})
        assert "SEE ALSO" in result.stripped_sections
        assert "Career" in result.kept_sections

    def test_strips_subsections_of_matched_header(self):
        wikitext = """\
Lead.

== References ==
Refs here.

=== Footnotes ===
Footnotes here.

=== Citations ===
Citations here.

== Career ==
Career info.
"""
        result = strip_sections(wikitext, {"references"})
        assert "References" in result.stripped_sections
        assert "Footnotes" in result.stripped_sections
        assert "Citations" in result.stripped_sections
        assert "Career" in result.kept_sections
        assert "Career info" in result.cleaned_wikitext
        assert "Footnotes here" not in result.cleaned_wikitext

    def test_empty_strip_set_keeps_everything(self):
        result = strip_sections(SAMPLE_WIKITEXT, set())
        assert len(result.stripped_sections) == 0
        assert "Early life" in result.kept_sections

    def test_empty_wikitext(self):
        result = strip_sections("", set())
        assert result.cleaned_wikitext.strip() == ""
        assert result.stripped_sections == []

    def test_wikitext_with_only_lead(self):
        result = strip_sections("Just a lead paragraph.", {"references"})
        assert "Just a lead paragraph" in result.cleaned_wikitext
        assert result.stripped_sections == []

    def test_strips_html_in_parallel(self):
        result = strip_sections(SAMPLE_WIKITEXT, STRIP_SET, html=SAMPLE_HTML)
        assert "Career information here" in result.cleaned_html
        assert "Other article" not in result.cleaned_html
        assert "Childhood" in result.cleaned_html

    def test_empty_html_returns_empty(self):
        result = strip_sections(SAMPLE_WIKITEXT, set(), html="")
        assert result.cleaned_html == ""


class TestStripSectionsFromHtml:
    def test_strips_by_heading_text(self):
        cleaned = strip_sections_from_html(SAMPLE_HTML, STRIP_SET)
        assert "Career information here" in cleaned
        assert "Other article" not in cleaned

    def test_strips_subsections(self):
        html = """\
<p>Lead text.</p>
<h2><span class="mw-headline" id="Refs">References</span></h2>
<p>Refs content.</p>
<h3><span class="mw-headline" id="Notes">Notes</span></h3>
<p>Notes content.</p>
<h2><span class="mw-headline" id="Career">Career</span></h2>
<p>Career content.</p>
"""
        cleaned = strip_sections_from_html(html, {"references"})
        assert "Refs content" not in cleaned
        assert "Notes content" not in cleaned
        assert "Career content" in cleaned

    def test_empty_strip_set(self):
        cleaned = strip_sections_from_html(SAMPLE_HTML, set())
        assert cleaned == SAMPLE_HTML

    def test_case_insensitive(self):
        html = """\
<p>Lead.</p>
<h2><span class="mw-headline" id="SEE_ALSO">SEE ALSO</span></h2>
<p>Links.</p>
"""
        cleaned = strip_sections_from_html(html, {"see also"})
        assert "Links" not in cleaned
        assert "Lead" in cleaned


class TestRepositionInfobox:
    def test_moves_infobox_before_first_h2(self):
        html = (
            '<table class="infobox"><tr><td>Data</td></tr></table>'
            '<p>Lead paragraph.</p>'
            '<h2>Section One</h2>'
            '<p>Body text.</p>'
        )
        result = reposition_infobox(html)
        h2_pos = result.index("<h2>")
        wrapper_pos = result.index("infobox-print-wrapper")
        lead_pos = result.index("Lead paragraph")
        # Lead should come before the wrapper
        assert lead_pos < wrapper_pos
        # Wrapper should come before first h2
        assert wrapper_pos < h2_pos

    def test_wraps_in_print_wrapper(self):
        html = (
            '<table class="infobox"><tr><td>X</td></tr></table>'
            '<p>Lead.</p>'
            '<h2>Section</h2>'
        )
        result = reposition_infobox(html)
        assert "infobox-print-wrapper" in result

    def test_no_infobox_unchanged(self):
        html = '<p>Just text.</p><h2>Section</h2>'
        assert reposition_infobox(html) == html

    def test_handles_nested_tables(self):
        html = (
            '<table class="infobox">'
            '<tr><td><table><tr><td>Nested</td></tr></table></td></tr>'
            '</table>'
            '<p>Lead.</p>'
            '<h2>Section</h2>'
        )
        result = reposition_infobox(html)
        assert "Nested" in result
        assert "infobox-print-wrapper" in result
        # The nested table should be fully contained
        assert result.count("<table") == result.count("</table>")

    def test_no_h2_appends_at_end(self):
        html = (
            '<table class="infobox"><tr><td>Data</td></tr></table>'
            '<p>Just lead text, no sections.</p>'
        )
        result = reposition_infobox(html)
        assert result.endswith("</div>")

    def test_strips_caption_and_image_row_and_leaves_no_residue(self):
        # Realistic infobox shape: <caption>, infobox-image row, then data rows.
        # This also guards the slice-length bug: stripping shrinks the table,
        # so the original-position removal must use the *extracted* length,
        # not the stripped length, or trailing markup leaks into html_without.
        html = (
            '<table class="infobox">'
            '<caption>Earth</caption>'
            '<tr><td class="infobox-image">'
            '<img src="//upload/earth.jpg" alt="Earth" />'
            '</td></tr>'
            '<tr><th>Aphelion</th><td>152,097,597 km</td></tr>'
            '<tr><th>Perihelion</th><td>147,098,450 km</td></tr>'
            '</table>'
            '<p>Earth is the third planet from the Sun.</p>'
            '<h2>Etymology</h2>'
            '<p>The word "Earth" derives from...</p>'
        )
        result = reposition_infobox(html)

        # Caption and image row gone from the wrapped output
        assert "<caption>" not in result
        assert "infobox-image" not in result
        assert "earth.jpg" not in result

        # Data rows preserved
        assert "Aphelion" in result
        assert "Perihelion" in result

        # No residue: the original infobox slot must be fully gone, with no
        # stray "</td></tr></table>" fragments before the lead paragraph.
        wrapper_start = result.index('<div class="infobox-print-wrapper">')
        head = result[:wrapper_start]
        assert "<table" not in head
        assert "</table>" not in head
        assert "</tr>" not in head
        assert "</td>" not in head

        # Tables stay balanced overall
        assert result.count("<table") == result.count("</table>")
        assert "infobox-print-wrapper" in result
