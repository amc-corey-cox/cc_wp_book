"""Load and validate the pipeline manifest."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent.parent / "manifest.yaml"

REQUIRED_STRIP = {
    "references",
    "see also",
    "further reading",
    "external links",
    "in popular culture",
    "notes",
    "gallery",
}


@dataclass
class TrimSize:
    width_in: float = 6.0
    height_in: float = 9.0


@dataclass
class VolumeConfig:
    count: int = 5
    balance_by: str = "content_length"
    trim_size: TrimSize = field(default_factory=TrimSize)
    bleed_in: float = 0.125


@dataclass
class TypographyConfig:
    body_font: str = "Libre Baskerville"
    heading_font: str = "Source Sans Pro"
    body_size_pt: int = 10
    line_height: float = 1.4


@dataclass
class ApiConfig:
    user_agent: str = "cc-wp-book/0.1.0"
    rate_limit_rps: int = 5
    retry_attempts: int = 3
    retry_backoff_seconds: int = 2


@dataclass
class CalloutConfig:
    enabled: bool = True
    qr_code: bool = True
    qr_size_in: float = 0.75


@dataclass
class ArticleOverride:
    extra_strip: list[str] = field(default_factory=list)
    keep: list[str] = field(default_factory=list)


@dataclass
class Manifest:
    strip_sections: list[str] = field(default_factory=lambda: list(REQUIRED_STRIP))
    optional_strip_sections: list[dict[str, Any]] = field(default_factory=list)
    article_overrides: dict[str, ArticleOverride] = field(default_factory=dict)
    volumes: VolumeConfig = field(default_factory=VolumeConfig)
    typography: TypographyConfig = field(default_factory=TypographyConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    callout: CalloutConfig = field(default_factory=CalloutConfig)
    draft_articles: list[str] = field(default_factory=list)

    def sections_to_strip(self, article_title: str | None = None) -> set[str]:
        """Return the normalized set of section headers to strip for a given article."""
        base = {s.lower() for s in self.strip_sections}

        for opt in self.optional_strip_sections:
            if opt.get("enabled", False):
                base.add(opt["name"].lower())

        if article_title and article_title in self.article_overrides:
            override = self.article_overrides[article_title]
            base |= {s.lower() for s in override.extra_strip}
            base -= {s.lower() for s in override.keep}

        return base


def load_manifest(path: Path | str | None = None) -> Manifest:
    """Load manifest from YAML file. Falls back to defaults if path is None."""
    if path is None:
        path = DEFAULT_MANIFEST
    path = Path(path)

    if not path.exists():
        return Manifest()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    overrides = {}
    for title, ov_data in (raw.get("article_overrides") or {}).items():
        if ov_data:
            overrides[title] = ArticleOverride(
                extra_strip=ov_data.get("extra_strip", []),
                keep=ov_data.get("keep", []),
            )

    vol_data = raw.get("volumes") or {}
    trim_data = vol_data.pop("trim_size", None) or {}
    volumes = VolumeConfig(
        trim_size=TrimSize(**trim_data),
        **{k: v for k, v in vol_data.items() if k in VolumeConfig.__dataclass_fields__},
    )

    def _from_dict(cls, data):
        data = data or {}
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    return Manifest(
        strip_sections=raw.get("strip_sections", list(REQUIRED_STRIP)),
        optional_strip_sections=raw.get("optional_strip_sections", []),
        article_overrides=overrides,
        volumes=volumes,
        typography=_from_dict(TypographyConfig, raw.get("typography")),
        api=_from_dict(ApiConfig, raw.get("api")),
        callout=_from_dict(CalloutConfig, raw.get("callout")),
        draft_articles=raw.get("draft_articles", []),
    )
