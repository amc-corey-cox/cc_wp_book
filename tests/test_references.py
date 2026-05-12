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
        assert format_compact(c) == (
            "Wilkinson, J. (2009). <i>New Eyes on the Sun</i>. Springer."
        )

    def test_book_with_chapter(self):
        c = Citation(
            type="book", author="Smith, J.", year="2010",
            chapter="Origins", title="Big Book", container="Penguin",
        )
        assert format_compact(c) == (
            'Smith, J. (2010). "Origins". In <i>Big Book</i>. Penguin.'
        )


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


class TestAuthorEditorEdgeCases:
    def test_author_last_only_no_initials(self):
        # When `last=` is present but `first=` is missing, the rendered
        # author should be just "Last." — no trailing comma.
        wikitext = '<ref>{{cite book |last=Wilkinson |year=2009 |title=T}}</ref>'
        cmap = extract_citation_map(wikitext)
        assert cmap[1].author == "Wilkinson"
        rendered = format_compact(cmap[1])
        assert "Wilkinson," not in rendered  # no trailing comma artifact
        assert rendered.startswith("Wilkinson.")

    def test_editor_last_only_no_initials(self):
        wikitext = (
            "<ref>{{cite book |editor-last=Smith |year=2010"
            " |title=T |publisher=P}}</ref>"
        )
        cmap = extract_citation_map(wikitext)
        assert cmap[1].author == "Smith (ed.)"


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
            "<ref>{{cite book |last=Rohli |first=R. |year=2018"
            " |title=Climatology |page=49}}</ref>"
            "<ref>{{cite book |last=Rohli |first=R. |year=2018"
            " |title=Climatology |page=32}}</ref>"
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

    def test_grouped_refs_excluded_from_map(self):
        # Refs with group="..." belong to Notes-style separate lists and
        # must NOT appear in the citations map — they're left untouched
        # in their own <ol>.
        wikitext = (
            '<ref name="body-ref">{{cite web |title=Body |year=2020}}</ref>'
            '<ref name="note1" group="n">An explanatory note.</ref>'
            '<ref name="body-ref-2">{{cite web |title=Body2 |year=2021}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        # Only the two body refs are in the map; positions are sequential
        # over default-group refs (named first).
        titles = sorted(c.title for c in cmap.values() if c.title)
        assert titles == ["Body", "Body2"]

    def test_refs_inside_grouped_reflist_excluded(self):
        # <ref> tags declared inside {{reflist|group=...|refs=...}} inherit
        # the parent's group even without their own group attribute.
        wikitext = (
            '<ref name="body">{{cite web |title=Body |year=2020}}</ref>'
            '{{reflist |group=n |refs='
            '<ref name="note">An explanatory note.</ref>'
            '<ref>Anonymous note inside reflist.</ref>'
            '}}'
            '<ref name="body2">{{cite web |title=Body2 |year=2021}}</ref>'
        )
        cmap = extract_citation_map(wikitext)
        titles = sorted(c.title for c in cmap.values() if c.title)
        assert titles == ["Body", "Body2"]
        # Notes content should NOT be in the map
        for c in cmap.values():
            assert c.raw_html != "An explanatory note."
            assert c.raw_html != "Anonymous note inside reflist."

    def test_grouped_name_first_seen_without_group_attr(self):
        # Tricky case: first body occurrence is `<ref name="X" />` (no
        # group attr), declaration is later inside a grouped reflist.
        # Wikipedia treats the name as belonging to the reflist's group,
        # and so should we.
        wikitext = (
            '<ref name="body">{{cite web |title=Body |year=2020}}</ref>'
            '<ref name="note" />'
            '{{reflist |group=n |refs='
            '<ref name="note">An explanatory note.</ref>'
            '}}'
        )
        cmap = extract_citation_map(wikitext)
        # "note" should NOT appear in the map — it's grouped via reflist.
        titles = sorted(c.title for c in cmap.values() if c.title)
        assert titles == ["Body"]


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

    def test_shortened_no_author_uses_container(self):
        # Repeated no-author web ref should use container as the short id,
        # not degenerate to just '(YYYY).' which is unhelpful.
        c = Citation(
            type="web", year="2013",
            title="Atmospheres and Planetary Temperatures",
            container="American Chemical Society",
        )
        assert format_shortened(c) == (
            "<i>American Chemical Society</i> (2013)."
        )

    def test_shortened_no_author_no_container_uses_title(self):
        c = Citation(type="web", year="2020", title="Some Page")
        assert format_shortened(c) == '"Some Page" (2020).'

    def test_render_first_full_subsequent_short(self):
        def rohli(pages):
            return Citation(
                type="book", author="Rohli, R. V. et al.", year="2018",
                title="Climatology", container="Jones & Bartlett", pages=pages,
            )

        cites = {
            1: rohli("p. 49"),
            2: rohli("p. 32"),
            3: rohli("p. 159"),
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
        def smith(pages):
            return Citation(
                type="book", author="Smith, J.", year="2010",
                title="T", pages=pages,
            )

        cites = {10: smith("p. 99"), 5: smith("p. 1")}
        rendered = render_citations(cites)
        assert "<i>T</i>" in rendered[5]  # canonical
        assert rendered[10] == "Smith (2010), p. 99."  # short form


class TestRewriteReferencesInplace:
    def test_rewrites_named_li_by_name_match(self):
        wikitext = (
            '<ref name="body">{{cite web |title=Body |year=2020 |website=W}}</ref>'
        )
        html = (
            '<h2>References</h2>'
            '<ol class="references">'
            '<li id="cite_note-body-1">old content</li>'
            '</ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert "old content" not in result
        assert "Body" in result
        assert 'id="cite_note-body-1"' in result

    def test_leaves_notes_ol_untouched(self):
        # The <ol> immediately following <h2>Notes</h2> is left alone —
        # Notes-section work is deferred. Only the References <ol> is
        # rewritten.
        wikitext = (
            '<ref name="body">{{cite web |title=BodyTitle |year=2020}}</ref>'
            '<ref name="explanation" group="n">An explanatory note.</ref>'
        )
        html = (
            '<h2>Notes</h2>'
            '<ol class="references">'
            '<li id="cite_note-explanation-1">original note text — keep me</li>'
            '</ol>'
            '<h2>References</h2>'
            '<ol class="references">'
            '<li id="cite_note-body-2">old body ref</li>'
            '</ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert "original note text — keep me" in result
        assert "old body ref" not in result
        assert "BodyTitle" in result

    def test_anonymous_li_matched_by_position(self):
        wikitext = (
            '<ref>{{cite web |title=AnonA |year=2020 |website=W}}</ref>'
            '<ref>{{cite web |title=AnonB |year=2021 |website=W}}</ref>'
        )
        html = (
            '<h2>References</h2>'
            '<ol class="references">'
            '<li id="cite_note-1">old A</li>'
            '<li id="cite_note-2">old B</li>'
            '</ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert "old A" not in result
        assert "old B" not in result
        assert "AnonA" in result
        assert "AnonB" in result

    def test_unmapped_named_li_unchanged(self):
        wikitext = (
            '<ref name="known">{{cite web |title=Known |year=2020}}</ref>'
        )
        html = (
            '<h2>References</h2>'
            '<ol class="references">'
            '<li id="cite_note-known-1">replace me</li>'
            '<li id="cite_note-mystery-2">leave me alone</li>'
            '</ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert "replace me" not in result
        assert "Known" in result
        assert "leave me alone" in result

    def test_handles_html_entity_encoded_ids(self):
        wikitext = '<ref name="foo">{{cite web |title=Found |year=2020}}</ref>'
        html = (
            '<h2>References</h2>'
            '<ol class="references"><li id="cite&#95;note-foo-1">old</li></ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert "old" not in result
        assert "Found" in result

    def test_no_default_refs_no_changes(self):
        wikitext = '<ref name="x" group="n">A note.</ref>'
        html = (
            '<h2>References</h2>'
            '<ol class="references"><li id="cite_note-x-1">content</li></ol>'
        )
        result = rewrite_references_inplace(html, wikitext)
        assert result == html
