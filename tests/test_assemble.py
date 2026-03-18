"""Tests for volume balancing logic."""

import pytest

from cc_wp_book.assemble import ArticleEntry, Volume, balance_volumes, front_matter_html


class TestBalanceVolumes:
    def test_empty_articles(self):
        volumes = balance_volumes([], num_volumes=3)
        assert len(volumes) == 3
        assert all(v.total_length == 0 for v in volumes)

    def test_single_article(self):
        articles = [ArticleEntry(title="Earth", content_length=1000)]
        volumes = balance_volumes(articles, num_volumes=3)
        total = sum(v.total_length for v in volumes)
        assert total == 1000

    def test_even_distribution_by_count(self):
        articles = [
            ArticleEntry(title=f"Article {i}", content_length=100)
            for i in range(10)
        ]
        volumes = balance_volumes(articles, num_volumes=5, balance_by="article_count")
        counts = [len(v.articles) for v in volumes]
        assert all(c == 2 for c in counts)

    def test_balanced_by_length(self):
        articles = [
            ArticleEntry(title="Big", content_length=10000),
            ArticleEntry(title="Medium", content_length=5000),
            ArticleEntry(title="Small1", content_length=2000),
            ArticleEntry(title="Small2", content_length=2000),
            ArticleEntry(title="Small3", content_length=1000),
        ]
        volumes = balance_volumes(articles, num_volumes=3, balance_by="content_length")
        lengths = sorted([v.total_length for v in volumes])
        # The greedy algorithm should produce a reasonable balance
        assert max(lengths) <= 11000
        assert sum(lengths) == 20000

    def test_invalid_num_volumes(self):
        with pytest.raises(ValueError):
            balance_volumes([], num_volumes=0)

    def test_more_volumes_than_articles(self):
        articles = [ArticleEntry(title="Only", content_length=100)]
        volumes = balance_volumes(articles, num_volumes=5)
        non_empty = [v for v in volumes if len(v.articles) > 0]
        assert len(non_empty) == 1

    def test_volume_numbering(self):
        volumes = balance_volumes([], num_volumes=5)
        numbers = [v.number for v in volumes]
        assert numbers == [1, 2, 3, 4, 5]


class TestFrontMatter:
    def test_contains_attribution(self):
        vol = Volume(number=1, articles=[ArticleEntry(title="Earth", content_length=0)])
        html = front_matter_html(vol, total_volumes=5)
        assert "Creative Commons" in html
        assert "CC BY-SA" in html

    def test_contains_volume_info(self):
        vol = Volume(number=2, articles=[])
        html = front_matter_html(vol, total_volumes=5)
        assert "Volume 2 of 5" in html

    def test_contains_methodology(self):
        vol = Volume(number=1, articles=[])
        html = front_matter_html(vol, total_volumes=1)
        assert "Methodology" in html
        assert "Wikimedia Foundation" in html

    def test_contains_article_listing(self):
        vol = Volume(
            number=1,
            articles=[
                ArticleEntry(title="Earth", content_length=100),
                ArticleEntry(title="Moon", content_length=200),
            ],
        )
        html = front_matter_html(vol, total_volumes=1)
        assert "Earth" in html
        assert "Moon" in html
