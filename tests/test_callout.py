"""Tests for callout box generation."""


from cc_wp_book.callout import _article_url, generate_callout_html


class TestArticleUrl:
    def test_simple_title(self):
        assert _article_url("Earth") == "https://en.wikipedia.org/wiki/Earth"

    def test_title_with_spaces(self):
        url = _article_url("Albert Einstein")
        assert url == "https://en.wikipedia.org/wiki/Albert_Einstein"

    def test_title_with_special_chars(self):
        url = _article_url("Rock & Roll")
        assert "Rock" in url
        assert "Roll" in url


class TestGenerateCalloutHtml:
    def test_includes_all_stripped_sections(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=["References", "See also", "External links"],
            include_qr=False,
        )
        assert "References" in html
        assert "See also" in html
        assert "External links" in html

    def test_includes_wikipedia_url(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=["References"],
            include_qr=False,
        )
        assert "wikipedia.org/wiki/Earth" in html

    def test_correct_url_for_spaced_title(self):
        html = generate_callout_html(
            title="Albert Einstein",
            stripped_sections=["References"],
            include_qr=False,
        )
        assert "wikipedia.org/wiki/Albert_Einstein" in html

    def test_empty_sections_returns_empty(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=[],
            include_qr=False,
        )
        assert html == ""

    def test_qr_code_included(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=["References"],
            include_qr=True,
            qr_size_in=0.75,
        )
        assert "data:image/png;base64," in html
        assert "callout-qr" in html

    def test_qr_code_excluded(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=["References"],
            include_qr=False,
        )
        assert "callout-qr" not in html

    def test_has_callout_class(self):
        html = generate_callout_html(
            title="Earth",
            stripped_sections=["References"],
            include_qr=False,
        )
        assert "stripped-sections-callout" in html
