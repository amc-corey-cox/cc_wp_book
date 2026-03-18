"""Tests for the article cache."""

from cc_wp_book.cache import ArticleCache


class TestArticleCache:
    def test_save_and_load(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        data = {"title": "Earth", "wikitext": "...", "html": "<p>...</p>"}
        cache.save("Earth", data)
        loaded = cache.load("Earth")
        assert loaded == data

    def test_has(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        assert not cache.has("Earth")
        cache.save("Earth", {"title": "Earth"})
        assert cache.has("Earth")

    def test_load_missing(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        assert cache.load("Nonexistent") is None

    def test_vital_list(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        assert cache.load_vital_list() is None
        cache.save_vital_list(["Earth", "Moon"])
        assert cache.load_vital_list() == ["Earth", "Moon"]

    def test_cached_titles(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        cache.save("Earth", {"title": "Earth"})
        cache.save("Moon", {"title": "Moon"})
        titles = cache.cached_titles()
        assert "Earth" in titles
        assert "Moon" in titles

    def test_title_with_spaces(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        cache.save("Albert Einstein", {"title": "Albert Einstein"})
        assert cache.has("Albert Einstein")
        loaded = cache.load("Albert Einstein")
        assert loaded["title"] == "Albert Einstein"

    def test_image_path(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        path = cache.image_path("Earth", "Earth_photo.jpg")
        assert path.suffix == ".jpg"
        assert "Earth" in path.name

    def test_has_image(self, tmp_path):
        cache = ArticleCache(tmp_path / "cache")
        assert not cache.has_image("Earth", "earth.jpg")
        img_path = cache.image_path("Earth", "earth.jpg")
        img_path.write_bytes(b"fake image data")
        assert cache.has_image("Earth", "earth.jpg")
