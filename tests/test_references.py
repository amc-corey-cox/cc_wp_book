"""Tests for compact CS1-style citation rendering."""

from cc_wp_book.references import (
    Citation,
    extract_citations,
    format_compact,
    rewrite_references_section,
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


class TestExtractCitations:
    def test_named_ref_with_cite_book(self):
        wikitext = (
            "Body text.<ref name=\"x\">{{cite book |last=Wilkinson |first=John "
            "|year=2009 |title=New Eyes on the Sun |publisher=Springer}}</ref>"
        )
        cites = extract_citations(wikitext)
        assert len(cites) == 1
        assert cites[0].type == "book"
        assert cites[0].author == "Wilkinson, J."
        assert cites[0].year == "2009"
        assert cites[0].title == "New Eyes on the Sun"
        assert cites[0].container == "Springer"

    def test_named_reuse_does_not_duplicate(self):
        wikitext = (
            "<ref name=\"a\">{{cite web |title=T |website=W |year=2020}}</ref>"
            "More text.<ref name=\"a\" />"
            "Even more.<ref name=\"a\" />"
        )
        cites = extract_citations(wikitext)
        assert len(cites) == 1

    def test_anonymous_ref_each_counted(self):
        wikitext = (
            "<ref>{{cite web |title=A |website=Site1 |year=2020}}</ref>"
            "<ref>{{cite web |title=B |website=Site2 |year=2021}}</ref>"
        )
        cites = extract_citations(wikitext)
        assert len(cites) == 2
        assert cites[0].title == "A"
        assert cites[1].title == "B"

    def test_document_order_preserved(self):
        wikitext = (
            "<ref name=\"first\">{{cite web |title=First |year=2020}}</ref>"
            "<ref name=\"second\">{{cite web |title=Second |year=2021}}</ref>"
            "<ref name=\"first\" />"
            "<ref name=\"third\">{{cite web |title=Third |year=2022}}</ref>"
        )
        cites = extract_citations(wikitext)
        assert [c.title for c in cites] == ["First", "Second", "Third"]

    def test_multiple_authors_get_et_al(self):
        wikitext = (
            "<ref>{{cite journal "
            "|last1=Argus |first1=D. F. "
            "|last2=Gordon |first2=R. G. "
            "|year=2011 |title=Plate motions |journal=GGG}}</ref>"
        )
        cites = extract_citations(wikitext)
        assert cites[0].author == "Argus, D. F. et al."

    def test_year_extracted_from_date(self):
        wikitext = (
            "<ref>{{cite web |title=T |website=W |date=18 July 2013}}</ref>"
        )
        cites = extract_citations(wikitext)
        assert cites[0].year == "2013"

    def test_url_and_archive_fields_dropped(self):
        wikitext = (
            "<ref>{{cite web |title=T |website=W |year=2013 "
            "|url=https://example.com |archive-url=https://web.archive.org/x "
            "|access-date=3 January 2023 |archive-date=27 January 2023}}</ref>"
        )
        cites = extract_citations(wikitext)
        rendered = format_compact(cites[0])
        assert "http" not in rendered
        assert "archive" not in rendered.lower()
        assert "retrieved" not in rendered.lower()
        assert "access" not in rendered.lower()

    def test_free_text_ref(self):
        wikitext = (
            "<ref>This is an explanatory footnote, not a citation.</ref>"
        )
        cites = extract_citations(wikitext)
        assert cites[0].type == "free"
        assert "explanatory footnote" in (cites[0].raw_html or "")

    def test_self_closing_only_no_content_skipped(self):
        wikitext = "Body.<ref name=\"x\" />"
        cites = extract_citations(wikitext)
        assert cites == []


class TestRewriteReferencesSection:
    def test_replaces_existing_ol(self):
        html = (
            "<p>Body.</p>"
            '<ol class="references"><li id="cite_note-1">old</li></ol>'
        )
        cites = [Citation(type="free", raw_html="new entry")]
        result = rewrite_references_section(html, cites)
        assert "old" not in result
        assert "new entry" in result
        assert '<ol class="references">' in result
        assert 'id="cite_note-1"' in result

    def test_consolidates_multiple_blocks(self):
        html = (
            '<ol class="references"><li>notes</li></ol>'
            "<p>Body.</p>"
            '<ol class="references"><li>refs</li></ol>'
        )
        cites = [Citation(type="free", raw_html="x")]
        result = rewrite_references_section(html, cites)
        assert result.count('<ol class="references">') == 1

    def test_no_citations_strips_existing_ol(self):
        html = '<p>Body.</p><ol class="references"><li>old</li></ol>'
        result = rewrite_references_section(html, [])
        assert '<ol class="references">' not in result
        assert "old" not in result

    def test_no_existing_ol_unchanged(self):
        html = "<p>Body.</p>"
        cites = [Citation(type="free", raw_html="x")]
        result = rewrite_references_section(html, cites)
        assert result == html
