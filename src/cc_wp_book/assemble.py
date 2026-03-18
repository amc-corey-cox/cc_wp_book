"""Assemble articles into balanced volumes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArticleEntry:
    title: str
    content_length: int
    html: str = ""


@dataclass
class Volume:
    number: int
    articles: list[ArticleEntry] = field(default_factory=list)

    @property
    def total_length(self) -> int:
        return sum(a.content_length for a in self.articles)


def balance_volumes(
    articles: list[ArticleEntry],
    num_volumes: int = 5,
    balance_by: str = "content_length",
) -> list[Volume]:
    """Distribute articles across volumes, balanced by the chosen metric.

    Uses a greedy algorithm: sort articles by size descending, assign each
    to the volume with the smallest current total.
    """
    if num_volumes <= 0:
        raise ValueError("num_volumes must be positive")
    if not articles:
        return [Volume(number=i + 1) for i in range(num_volumes)]

    volumes = [Volume(number=i + 1) for i in range(num_volumes)]

    if balance_by == "article_count":
        # Simple round-robin
        for i, article in enumerate(articles):
            volumes[i % num_volumes].articles.append(article)
    else:
        # Greedy by content_length
        sorted_articles = sorted(articles, key=lambda a: a.content_length, reverse=True)
        for article in sorted_articles:
            lightest = min(volumes, key=lambda v: v.total_length)
            lightest.articles.append(article)

    return volumes


def front_matter_html(volume: Volume, total_volumes: int) -> str:
    """Generate front matter HTML for a volume with attribution."""
    return f"""<div class="front-matter">
  <h1>Wikipedia Vital Articles</h1>
  <h2>Volume {volume.number} of {total_volumes}</h2>

  <div class="attribution">
    <h3>Attribution &amp; License</h3>
    <p>The content in this volume is derived from Wikipedia, the free encyclopedia,
    and is licensed under the
    <a href="https://creativecommons.org/licenses/by-sa/4.0/">Creative Commons
    Attribution-ShareAlike 4.0 International License</a> (CC BY-SA 4.0).</p>

    <p>Original articles were written by thousands of Wikipedia contributors.
    Full revision histories and contributor lists are available on each article's
    Wikipedia page.</p>

    <h3>Methodology</h3>
    <p>This volume was generated from Wikipedia's list of 1,000 Vital Articles.
    Certain sections were removed to focus on encyclopedic content suitable for
    print. Removed sections are documented in each article's callout box, which
    includes a QR code and URL linking to the full article on Wikipedia.</p>

    <p>The complete methodology, including which sections were removed and why,
    is documented in the project's open-source manifest file.</p>

    <p>All markup from sales of this book goes to the Wikimedia Foundation.</p>
  </div>

  <div class="toc">
    <h3>Contents</h3>
    <ol>
      {"".join(f"<li>{a.title}</li>" for a in volume.articles)}
    </ol>
  </div>
</div>
"""
