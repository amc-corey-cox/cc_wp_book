"""Tests for manifest loading and configuration."""


import yaml

from cc_wp_book.config import (
    ArticleOverride,
    Manifest,
    load_manifest,
)


class TestLoadManifest:
    def test_load_defaults_when_no_file(self, tmp_path):
        manifest = load_manifest(tmp_path / "nonexistent.yaml")
        assert isinstance(manifest, Manifest)
        assert len(manifest.strip_sections) > 0

    def test_load_from_yaml(self, tmp_path):
        data = {
            "strip_sections": ["References", "See also"],
            "volumes": {"count": 3},
            "draft_articles": ["Earth"],
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(data))

        manifest = load_manifest(path)
        assert manifest.strip_sections == ["References", "See also"]
        assert manifest.volumes.count == 3
        assert manifest.draft_articles == ["Earth"]

    def test_article_overrides(self, tmp_path):
        data = {
            "strip_sections": ["References"],
            "article_overrides": {
                "Earth": {
                    "extra_strip": ["Geology"],
                    "keep": ["References"],
                }
            },
        }
        path = tmp_path / "test.yaml"
        path.write_text(yaml.dump(data))

        manifest = load_manifest(path)
        assert "Earth" in manifest.article_overrides
        assert manifest.article_overrides["Earth"].extra_strip == ["Geology"]
        assert manifest.article_overrides["Earth"].keep == ["References"]


class TestSectionsToStrip:
    def test_base_sections(self):
        manifest = Manifest(strip_sections=["References", "See also"])
        result = manifest.sections_to_strip()
        assert result == {"references", "see also"}

    def test_optional_sections_disabled(self):
        manifest = Manifest(
            strip_sections=["References"],
            optional_strip_sections=[{"name": "History", "enabled": False}],
        )
        result = manifest.sections_to_strip()
        assert "history" not in result

    def test_optional_sections_enabled(self):
        manifest = Manifest(
            strip_sections=["References"],
            optional_strip_sections=[{"name": "History", "enabled": True}],
        )
        result = manifest.sections_to_strip()
        assert "history" in result

    def test_article_override_extra_strip(self):
        manifest = Manifest(
            strip_sections=["References"],
            article_overrides={
                "Earth": ArticleOverride(extra_strip=["Geology"]),
            },
        )
        result = manifest.sections_to_strip("Earth")
        assert "geology" in result
        assert "references" in result

    def test_article_override_keep(self):
        manifest = Manifest(
            strip_sections=["References", "Notes"],
            article_overrides={
                "Earth": ArticleOverride(keep=["Notes"]),
            },
        )
        result = manifest.sections_to_strip("Earth")
        assert "references" in result
        assert "notes" not in result

    def test_no_override_for_other_articles(self):
        manifest = Manifest(
            strip_sections=["References"],
            article_overrides={
                "Earth": ArticleOverride(extra_strip=["Geology"]),
            },
        )
        result = manifest.sections_to_strip("Moon")
        assert "geology" not in result
