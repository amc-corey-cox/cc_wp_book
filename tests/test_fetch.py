"""Tests for the Wikipedia API fetch module."""

import pytest
import responses

from cc_wp_book.config import ApiConfig
from cc_wp_book.fetch import (
    WIKIPEDIA_API,
    ArticleData,
    FetchError,
    RateLimiter,
    WikipediaClient,
)


@pytest.fixture
def client():
    config = ApiConfig(
        user_agent="test-agent/0.1",
        rate_limit_rps=100,
        retry_attempts=2,
        retry_backoff_seconds=0,
    )
    return WikipediaClient(config)


class TestRateLimiter:
    def test_first_call_immediate(self):
        rl = RateLimiter(rps=10)
        import time
        start = time.monotonic()
        rl.wait()
        elapsed = time.monotonic() - start
        assert elapsed < 0.1

    def test_zero_rps_no_delay(self):
        rl = RateLimiter(rps=0)
        rl.wait()
        rl.wait()


class TestWikipediaClient:
    @responses.activate
    def test_fetch_vital_articles_list(self, client):
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "parse": {
                    "links": [
                        {"ns": 0, "title": "Earth", "exists": True},
                        {"ns": 0, "title": "Moon", "exists": True},
                        {"ns": 4, "title": "Wikipedia:About",
                         "exists": True},
                        {"ns": 0, "title": "Redlink", "exists": False},
                    ]
                }
            },
        )

        titles = client.fetch_vital_articles_list()
        assert titles == ["Earth", "Moon"]

    @responses.activate
    def test_fetch_article(self, client):
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "parse": {
                    "pageid": 42,
                    "wikitext": "'''Earth''' is a planet.",
                    "text": "<p><b>Earth</b> is a planet.</p>",
                    "categories": [{"category": "Planets"}],
                }
            },
        )
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "query": {
                    "pages": [
                        {
                            "thumbnail": {
                                "source": "https://upload.wikimedia.org/earth.jpg",
                            },
                            "pageimage": "Earth_photo.jpg",
                        }
                    ]
                }
            },
        )

        article = client.fetch_article("Earth")
        assert article.title == "Earth"
        assert article.wikitext == "'''Earth''' is a planet."
        assert article.html == "<p><b>Earth</b> is a planet.</p>"
        assert article.page_id == 42
        assert article.lead_image_url == (
            "https://upload.wikimedia.org/earth.jpg"
        )
        assert article.lead_image_filename == "Earth_photo.jpg"

    @responses.activate
    def test_fetch_article_no_images(self, client):
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "parse": {
                    "pageid": 1,
                    "wikitext": "Some text.",
                    "text": "<p>Some text.</p>",
                    "categories": [],
                }
            },
        )
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={"query": {"pages": [{}]}},
        )

        article = client.fetch_article("Test")
        assert article.lead_image_url is None

    @responses.activate
    def test_api_error_raises(self, client):
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "error": {
                    "code": "nosuchpage", "info": "not found"
                }
            },
        )

        with pytest.raises(FetchError, match="API error"):
            client.fetch_vital_articles_list()

    @responses.activate
    def test_retry_on_failure(self, client):
        responses.add(responses.GET, WIKIPEDIA_API, status=500)
        responses.add(
            responses.GET,
            WIKIPEDIA_API,
            json={
                "parse": {
                    "links": [
                        {"ns": 0, "title": "Earth", "exists": True}
                    ]
                }
            },
        )

        titles = client.fetch_vital_articles_list()
        assert titles == ["Earth"]
        assert len(responses.calls) == 2

    @responses.activate
    def test_all_retries_exhausted(self, client):
        responses.add(responses.GET, WIKIPEDIA_API, status=500)
        responses.add(responses.GET, WIKIPEDIA_API, status=503)

        with pytest.raises(FetchError, match="All 2 attempts failed"):
            client.fetch_vital_articles_list()


class TestArticleDataSerialization:
    def test_round_trip(self):
        article = ArticleData(
            title="Earth",
            wikitext="'''Earth'''",
            html="<p><b>Earth</b></p>",
            page_id=42,
            lead_image_url="https://example.com/earth.jpg",
            categories=["Planets"],
        )
        d = article.to_dict()
        restored = ArticleData.from_dict(d)
        assert restored.title == article.title
        assert restored.html == article.html
        assert restored.page_id == article.page_id
