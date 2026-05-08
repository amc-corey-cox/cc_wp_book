"""Tests for compact CS1-style citation rendering."""

from cc_wp_book.references import (
    Citation,
    extract_citation_map,
    format_compact,
    format_shortened,
    render_citations,
    rewrite_references_inplace,
)


class TestFormatCompactBook:
    def test_book_basic(self):
        c = Citation(
            type="book", author="Wilkinson, J.", year="2009",
            title="New Eyes on the Sun", container="Springer",
        )
        assert format_compact(c) == 'Wilkinson, J. (2009). <i>New Eyes on the Sun</i>. Springer.'

    def test_book_with_chapter(self):
        c = Citation(
            type="book", author="Smith, J.", year="2010",
            chapter="Origins", title="Big Book", container="Penguin",
        )
        assert format_compact(c) == 'Smith, J. (2010). "Origins". In <i>Big Book</i>. Penguin.'


class TestFormatCompactJournal:
    def test_journal_with_volume_issue(self):
        c = Citation(
            type="journal", author="Argus, D. F. et al.", year="2011",
            title="Geologically current plate motions",
            container="Geophys J Int", volume="12", issue="11",
        )
        assert format_compact(c) == (
            'Argus, D. F. et al. (2011). "Geologically current plate motions". '
            '<i>Geophys J Int</i> 12(11).'
        )

    def test_journal_volume_no_issue(self):
        c = Citation(
            type="journal", author="Doe, J.", year="2020",
            title="Title", container="Nature", volume="500",
        )
        assert format_compact(c) == 'Doe, J. (2020). "Title". <i>Nature</i> 500.'


class TestFormatCompactWeb:
    def test_web_with_author(self):
        c = Citation(
            type="web", author="Smith, J.", year="2023",
            title="Earth Fact Sheet", container="NASA",
        )
        assert format_compact(c) == 'Smith, J. (2023). "Earth Fact Sheet". <i>NASA</i>.'

    def test_web_no_author_year_at_end(self):
        c = Citation(
            type="web", year="2013",
            title="Atmospheres and Planetary Temperatures",
            container="American Chemical Society",
        )
        assert format_compact(c) == (
            '"Atmospheres and Planetary Temperatures". '
            '<i>American Chemical Society</i>. (2013).'
        )


class TestFormatCompactNews:
    def test_news_with_author(self):
        c = Citation(
            type="news", author="Doe, J.", year="2024",
            title="Climate update", container="Reuters",
        )
        assert format_compact(c) == 'Doe, J. (2024). "Climate update". <i>Reuters</i>.'


class TestFormatCompactFreeText:
    def test_free_passes_raw_html(self):
        c = Citation(type="free", raw_html="Some inline footnote text.")
        assert format_compact(c) == "Some inline footnote text."


class TestExtractCitationMap:
    def test_named_ref_with_cite_book_at_position_one(self):
        wikitext = (
            'Body text.<ref name="x">{{cite book |last=Wilkinson |first=John '
            '|year=2009 |title=New Eyes on the Sun |publisher=Springer}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert list(cmap.keys()) == [1]
        c = cmap[1]
        assert c.type == "book"
        assert c.author == "Wilkinson, J."
        assert c.year == "2009"
        assert c.title == "New Eyes on the Sun"
        assert c.container == "Springer"

    def test_named_reuse_does_not_duplicate(self):
        wikitext = (
            '<ref name="a">{{cite web |title=T |website=W |year=2020}}</ref>'
            '<ref name="a" />'
            '<ref name="a" />'
        )
        cmap = extract_citation_map(wikitext)
        assert list(cmap.keys()) == [1]

    def test_anonymous_refs_each_distinct_even_if_identical(self):
        # Wikipedia treats each anonymous <ref> as its own entry — they often
        # differ in page= or other params even when "looks the same". We
        # match that behavior; only named-ref reuses dedupe.
        wikitext = (
            '<ref>{{cite book |last=Rohli |first=R. |year=2018 |title=Climatology |page=49}}</ref>'
            '<ref>{{cite book |last=Rohli |first=R. |year=2018 |title=Climatology |page=32}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert list(cmap.keys()) == [1, 2]
        assert cmap[1].pages == "p. 49"
        assert cmap[2].pages == "p. 32"

    def test_distinct_anonymous_each_get_position(self):
        wikitext = (
            '<ref>{{cite web |title=A |website=Site1 |year=2020}}</ref>'
            '<ref>{{cite web |title=B |website=Site2 |year=2021}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert list(cmap.keys()) == [1, 2]
        assert cmap[1].title == "A"
        assert cmap[2].title == "B"

    def test_document_order_preserved(self):
        wikitext = (
            '<ref name="first">{{cite web |title=First |year=2020}}</ref>'
            '<ref name="second">{{cite web |title=Second |year=2021}}</ref>'
            '<ref name="first" />'
            '<ref name="third">{{cite web |title=Third |year=2022}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert [cmap[i].title for i in [1, 2, 3]] == ["First", "Second", "Third"]

    def test_multiple_authors_get_et_al(self):
        wikitext = (
            '<ref>{{cite journal '
            '|last1=Argus |first1=D. F. '
            '|last2=Gordon |first2=R. G. '
            '|year=2011 |title=Plate motions |journal=GGG}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert cmap[1].author == "Argus, D. F. et al."

    def test_year_extracted_from_date(self):
        wikitext = '<ref>{{cite web |title=T |website=W |date=18 July 2013}}</ref>'
        cmap = extract_citation_map(wikitext)
        assert cmap[1].year == "2013"

    def test_url_and_archive_fields_dropped(self):
        wikitext = (
            '<ref>{{cite web |title=T |website=W |year=2013 '
            '|url=https://example.com |archive-url=https://web.archive.org/x '
            '|access-date=3 January 2023 |archive-date=27 January 2023}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        rendered = format_compact(cmap[1])
        assert "http" not in rendered
        assert "archive" not in rendered.lower()
        assert "retrieved" not in rendered.lower()
        assert "access" not in rendered.lower()

    def test_free_text_ref(self):
        wikitext = (
            '<ref>This is an explanatory footnote, not a citation.</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert cmap[1].type == "free"
        assert "explanatory footnote" in (cmap[1].raw_html or "")

    def test_self_closing_only_no_content_skipped(self):
        wikitext = 'Body.<ref name="x" />'
        cmap = extract_citation_map(wikitext)
        assert cmap == {}

    def test_grouped_refs_skipped(self):
        # Refs with group="..." belong to Notes-style separate lists and
        # are intentionally not rewritten — left in their original form.
        wikitext = (
            '<ref name="body-ref">{{cite web |title=Body |year=2020}}</ref>'
            '<ref name="note1" group="n">An explanatory note.</ref>'
            '<ref name="body-ref-2">{{cite web |title=Body2 |year=2021}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        assert list(cmap.keys()) == [1, 2]
        assert cmap[1].title == "Body"
        assert cmap[2].title == "Body2"


class TestShortenedAndRenderDedup:
    def test_shortened_form_book(self):
        c = Citation(
            type="book", author="Rohli, R. V. et al.", year="2018",
            title="Climatology", container="Jones & Bartlett",
            pages="p. 32",
        )
        assert format_shortened(c) == "Rohli et al. (2018), p. 32."

    def test_shortened_single_author(self):
        c = Citation(
            type="book", author="Smith, J.", year="2010",
            title="Geology", pages="p. 45",
        )
        assert format_shortened(c) == "Smith (2010), p. 45."

    def test_shortened_no_pages(self):
        c = Citation(type="book", author="Smith, J.", year="2010", title="T")
        assert format_shortened(c) == "Smith (2010)."

    def test_render_first_full_subsequent_short(self):
        cites = {
            1: Citation(type="book", author="Rohli, R. V. et al.", year="2018",
                        title="Climatology", container="Jones & Bartlett", pages="p. 49"),
            2: Citation(type="book", author="Rohli, R. V. et al.", year="2018",
                        title="Climatology", container="Jones & Bartlett", pages="p. 32"),
            3: Citation(type="book", author="Rohli, R. V. et al.", year="2018",
                        title="Climatology", container="Jones & Bartlett", pages="p. 159"),
        }
        rendered = render_citations(cites)
        assert "<i>Climatology</i>" in rendered[1]
        assert "Jones & Bartlett" in rendered[1]
        assert "p. 49" in rendered[1]
        assert rendered[2] == "Rohli et al. (2018), p. 32."
        assert rendered[3] == "Rohli et al. (2018), p. 159."

    def test_render_distinct_sources_each_full(self):
        cites = {
            1: Citation(type="book", author="Smith, J.", year="2010", title="A"),
            2: Citation(type="book", author="Jones, K.", year="2015", title="B"),
        }
        rendered = render_citations(cites)
        assert "<i>A</i>" in rendered[1]
        assert "<i>B</i>" in rendered[2]
        # Neither should be in shortened form
        assert "Smith (2010)" not in rendered[1] or "<i>" in rendered[1]
        assert "Jones (2015)" not in rendered[2] or "<i>" in rendered[2]

    def test_render_free_text_not_deduped(self):
        # Free-text refs are explanatory notes — never dedupe even if identical.
        cites = {
            1: Citation(type="free", raw_html="A note."),
            2: Citation(type="free", raw_html="A note."),
        }
        rendered = render_citations(cites)
        assert rendered[1] == "A note."
        assert rendered[2] == "A note."

    def test_render_uses_first_position_as_canonical(self):
        # If position 5 is the first appearance, position 10 is the repeat.
        # Walking sorted positions ensures lower positions get the full form.
        cites = {
            10: Citation(type="book", author="Smith, J.", year="2010", title="T", pages="p. 99"),
            5: Citation(type="book", author="Smith, J.", year="2010", title="T", pages="p. 1"),
        }
        rendered = render_citations(cites)
        assert "<i>T</i>" in rendered[5]  # canonical
        assert rendered[10] == "Smith (2010), p. 99."  # short form


class TestRewriteReferencesInplace:
    def test_replaces_li_content_when_position_matches(self):
        html = (
            '<ol class="references">'
            '<li id="cite_note-x-1">old content</li>'
            '<li id="cite_note-2">other old</li>'
            '</ol>'
        )
        cmap = {
            1: Citation(type="free", raw_html="new one"),
            2: Citation(type="free", raw_html="new two"),
        }
        result = rewrite_references_inplace(html, cmap)
        assert "old content" not in result
        assert "other old" not in result
        assert "new one" in result
        assert "new two" in result
        assert 'id="cite_note-x-1"' in result
        assert 'id="cite_note-2"' in result

    def test_leaves_unmapped_li_unchanged(self):
        html = (
            '<ol class="references">'
            '<li id="cite_note-x-1">replace me</li>'
            '<li id="cite_note-note1-2">explanatory footnote</li>'
            '</ol>'
        )
        cmap = {1: Citation(type="free", raw_html="new")}
        result = rewrite_references_inplace(html, cmap)
        assert "new" in result
        assert "replace me" not in result
        assert "explanatory footnote" in result  # untouched

    def test_handles_html_entity_encoded_ids(self):
        # Wikipedia HTML uses &#95; for _ in some contexts.
        html = '<li id="cite&#95;note-foo-1">old</li>'
        cmap = {1: Citation(type="free", raw_html="new")}
        result = rewrite_references_inplace(html, cmap)
        assert "new" in result
        assert "old" not in result

    def test_preserves_multiple_ol_blocks(self):
        # Notes section + References section — both should keep their
        # <ol> structure; only the entries we have data for get rewritten.
        html = (
            '<h2>Notes</h2>'
            '<ol class="references"><li id="cite_note-noteA-1">note one</li></ol>'
            '<h2>References</h2>'
            '<ol class="references"><li id="cite_note-mainref-2">main ref</li></ol>'
        )
        cmap = {2: Citation(type="free", raw_html="compact main")}
        result = rewrite_references_inplace(html, cmap)
        # Both <ol> blocks survive
        assert result.count('<ol class="references">') == 2
        # Notes <li> untouched
        assert "note one" in result
        # References <li> rewritten
        assert "compact main" in result
        assert "main ref" not in result

    def test_empty_map_no_changes(self):
        html = '<li id="cite_note-x-1">content</li>'
        result = rewrite_references_inplace(html, {})
        assert result == html
