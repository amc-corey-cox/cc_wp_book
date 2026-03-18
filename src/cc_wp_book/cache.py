"""Local file cache for fetched article data."""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _slug(title: str) -> str:
    return title.replace(" ", "_").replace("/", "_")


class ArticleCache:
    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.articles_dir = self.cache_dir / "articles"
        self.images_dir = self.cache_dir / "images"
        self.articles_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    def _article_path(self, title: str) -> Path:
        return self.articles_dir / f"{_slug(title)}.json"

    def has(self, title: str) -> bool:
        return self._article_path(title).exists()

    def save(self, title: str, data: dict) -> None:
        path = self._article_path(title)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        logger.debug("Cached: %s", title)

    def load(self, title: str) -> dict | None:
        path = self._article_path(title)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def image_path(self, title: str, filename: str) -> Path:
        """Return the cache path for a lead image."""
        ext = Path(filename).suffix or ".jpg"
        return self.images_dir / f"{_slug(title)}{ext}"

    def has_image(self, title: str, filename: str) -> bool:
        return self.image_path(title, filename).exists()

    def save_vital_list(self, titles: list[str]) -> None:
        path = self.cache_dir / "vital_articles.json"
        path.write_text(json.dumps(titles, indent=2))

    def load_vital_list(self) -> list[str] | None:
        path = self.cache_dir / "vital_articles.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def cached_titles(self) -> list[str]:
        titles = []
        for p in sorted(self.articles_dir.glob("*.json")):
            data = json.loads(p.read_text())
            titles.append(data.get("title", p.stem))
        return titles
