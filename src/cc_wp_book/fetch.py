"""Fetch article data from the Wikipedia / Wikimedia APIs."""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from cc_wp_book.config import ApiConfig

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
VITAL_ARTICLES_TITLE = "Wikipedia:Vital articles"


@dataclass
class ArticleData:
    title: str
    wikitext: str
    html: str
    page_id: int
    lead_image_url: str | None = None
    lead_image_filename: str | None = None
    categories: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ArticleData:
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })


class FetchError(Exception):
    pass


class RateLimiter:
    def __init__(self, rps: int = 5):
        self._min_interval = 1.0 / rps if rps > 0 else 0
        self._last_call = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self._last_call
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call = time.monotonic()


class WikipediaClient:
    def __init__(self, api_config: ApiConfig | None = None):
        config = api_config or ApiConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        self.rate_limiter = RateLimiter(config.rate_limit_rps)
        self.retry_attempts = config.retry_attempts
        self.retry_backoff = config.retry_backoff_seconds

    def _request(self, params: dict[str, Any]) -> dict:
        params.setdefault("format", "json")
        params.setdefault("formatversion", "2")

        last_exc = None
        for attempt in range(self.retry_attempts):
            self.rate_limiter.wait()
            try:
                resp = self.session.get(
                    WIKIPEDIA_API, params=params, timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise FetchError(f"API error: {data['error']}")
                return data
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < self.retry_attempts - 1:
                    wait = self.retry_backoff * (2 ** attempt)
                    logger.warning(
                        "Request failed (attempt %d/%d), "
                        "retrying in %ds: %s",
                        attempt + 1,
                        self.retry_attempts,
                        wait,
                        exc,
                    )
                    time.sleep(wait)

        raise FetchError(
            f"All {self.retry_attempts} attempts failed"
        ) from last_exc

    def fetch_vital_articles_list(self) -> list[str]:
        """Fetch the list of 1,000 Vital Articles from Wikipedia."""
        titles: list[str] = []
        params: dict[str, Any] = {
            "action": "parse",
            "page": VITAL_ARTICLES_TITLE,
            "prop": "links",
        }
        data = self._request(params)
        links = data.get("parse", {}).get("links", [])
        for link in links:
            ns = link.get("ns", 0)
            if ns == 0 and link.get("exists", False):
                titles.append(link["title"])
        logger.info("Found %d vital article links", len(titles))
        return titles

    def fetch_article(self, title: str) -> ArticleData:
        """Fetch wikitext, rendered HTML, and metadata for an article."""
        params = {
            "action": "parse",
            "page": title,
            "prop": "wikitext|text|categories",
        }
        data = self._request(params)
        parse = data.get("parse", {})

        wikitext = parse.get("wikitext", "")
        html = parse.get("text", "")
        page_id = parse.get("pageid", 0)
        categories = [
            c.get("category", "") for c in parse.get("categories", [])
        ]

        lead_image_url, lead_image_filename = self._fetch_lead_image(title)

        return ArticleData(
            title=title,
            wikitext=wikitext,
            html=html,
            page_id=page_id,
            lead_image_url=lead_image_url,
            lead_image_filename=lead_image_filename,
            categories=categories,
        )

    def _fetch_lead_image(self, title: str) -> tuple[str | None, str | None]:
        """Get the article's lead image via the pageimages API.

        Requests a thumbnail at 1200px wide (high enough for 300 DPI
        at ~4in print width) to avoid hotlink-blocking on raw originals.
        """
        params = {
            "action": "query",
            "titles": title,
            "prop": "pageimages",
            "piprop": "thumbnail|name",
            "pithumbsize": "1200",
        }
        data = self._request(params)
        pages = data.get("query", {}).get("pages", [])
        for page in pages:
            thumb = page.get("thumbnail", {})
            url = thumb.get("source")
            filename = page.get("pageimage")
            if url and filename:
                return url, filename
        return None, None

    def download_image(self, url: str, target_path: str) -> str:
        """Download an image to a local path. Returns the path."""
        self.rate_limiter.wait()
        resp = self.session.get(
            url, timeout=60, stream=True,
            headers={"User-Agent": (
                "Mozilla/5.0 (compatible; cc-wp-book/0.1.0; "
                "+https://github.com/OWNER/cc_wp_book)"
            )},
        )
        resp.raise_for_status()
        with open(target_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return target_path
