"""Command-line interface for the cc-wp-book pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from cc_wp_book.config import load_manifest

logger = logging.getLogger(__name__)


def _add_selection_args(parser: argparse.ArgumentParser) -> None:
    """Add article selection arguments shared by multiple commands."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--draft",
        action="store_true",
        help="Use draft articles from manifest",
    )
    group.add_argument(
        "--index",
        type=int,
        help="Select article N (1-based) from the vital articles list",
    )
    group.add_argument(
        "--article",
        type=str,
        help="Select a specific article by title",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Process all 1,000 vital articles",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cc-wp-book",
        description=(
            "Transform Wikipedia's Vital Articles "
            "into print-ready PDFs."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to manifest.yaml (default: ./manifest.yaml)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Output directory for generated files",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("cache"),
        help="Cache directory for downloaded articles",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    sub = parser.add_subparsers(dest="command")

    fetch_parser = sub.add_parser(
        "fetch", help="Fetch articles from Wikipedia API and cache locally"
    )
    _add_selection_args(fetch_parser)
    fetch_parser.add_argument(
        "--list-only",
        action="store_true",
        help="Only fetch/display the article list, not content",
    )
    fetch_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if already cached",
    )

    render_parser = sub.add_parser(
        "render", help="Render cached articles to PDF"
    )
    _add_selection_args(render_parser)

    pipe_parser = sub.add_parser(
        "pipeline", help="Fetch, parse, and render in one step"
    )
    _add_selection_args(pipe_parser)
    pipe_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if already cached",
    )

    assemble_parser = sub.add_parser(
        "assemble", help="Assemble cached articles into balanced volumes"
    )
    assemble_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if already cached",
    )

    sub.add_parser(
        "validate", help="Validate generated PDFs against print specs"
    )

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    manifest = load_manifest(args.manifest)

    commands = {
        "fetch": _cmd_fetch,
        "render": _cmd_render,
        "pipeline": _cmd_pipeline,
        "assemble": _cmd_assemble,
        "validate": _cmd_validate,
    }
    handler = commands.get(args.command)
    if handler:
        return handler(manifest, args)
    parser.print_help()
    return 0


def _resolve_titles(manifest, args, cache) -> list[str]:
    """Resolve which article titles to operate on."""
    from cc_wp_book.fetch import WikipediaClient

    if getattr(args, "article", None):
        return [args.article]

    if getattr(args, "draft", False):
        return manifest.draft_articles

    vital_list = cache.load_vital_list()
    if vital_list is None:
        logger.info("Fetching vital articles list...")
        client = WikipediaClient(manifest.api)
        vital_list = client.fetch_vital_articles_list()
        cache.save_vital_list(vital_list)
        logger.info("Cached %d vital article titles", len(vital_list))

    if getattr(args, "index", None) is not None:
        idx = args.index
        if idx < 1 or idx > len(vital_list):
            logger.error(
                "Index %d out of range (1-%d)", idx, len(vital_list)
            )
            return []
        return [vital_list[idx - 1]]

    if getattr(args, "all", False):
        return vital_list

    return manifest.draft_articles


def _fetch_articles(manifest, cache, titles, force=False) -> int:
    """Fetch, cache articles, and download lead images. Returns failure count."""
    from cc_wp_book.fetch import WikipediaClient

    client = WikipediaClient(manifest.api)
    failures = 0

    for title in titles:
        if cache.has(title) and not force:
            logger.info("Cached (skip): %s", title)
            continue
        logger.info("Fetching: %s", title)
        try:
            article = client.fetch_article(title)
            cache.save(title, article.to_dict())

            if article.lead_image_url and article.lead_image_filename:
                img_path = cache.image_path(
                    title, article.lead_image_filename
                )
                if not img_path.exists() or force:
                    logger.info("  Downloading image: %s", article.lead_image_filename)
                    client.download_image(
                        article.lead_image_url, str(img_path)
                    )
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", title, exc)
            failures += 1

    return failures


def _cmd_fetch(manifest, args) -> int:
    from cc_wp_book.cache import ArticleCache

    cache = ArticleCache(args.cache_dir)

    if args.list_only:
        titles = _resolve_titles(manifest, args, cache)
        for i, t in enumerate(titles, 1):
            print(f"{i:4d}. {t}")
        return 0

    titles = _resolve_titles(manifest, args, cache)
    if not titles:
        return 1

    _fetch_articles(manifest, cache, titles, args.force)
    return 0


def _cmd_render(manifest, args) -> int:
    from cc_wp_book.cache import ArticleCache

    cache = ArticleCache(args.cache_dir)
    titles = _resolve_titles(manifest, args, cache)
    if not titles:
        return 1

    return _render_articles(manifest, args, cache, titles)


def _cmd_pipeline(manifest, args) -> int:
    from cc_wp_book.cache import ArticleCache

    cache = ArticleCache(args.cache_dir)
    titles = _resolve_titles(manifest, args, cache)
    if not titles:
        return 1

    failures = _fetch_articles(
        manifest, cache, titles, getattr(args, "force", False)
    )
    if failures:
        return 1

    return _render_articles(manifest, args, cache, titles)


def _cmd_assemble(manifest, args) -> int:
    """Assemble all cached articles into balanced volumes."""
    from cc_wp_book.assemble import ArticleEntry, balance_volumes, front_matter_html
    from cc_wp_book.cache import ArticleCache
    from cc_wp_book.fetch import ArticleData
    from cc_wp_book.parse import strip_sections
    from cc_wp_book.render import render_article_html, render_pdf

    cache = ArticleCache(args.cache_dir)

    titles = cache.load_vital_list()
    if not titles:
        logger.error("No vital articles list cached — run 'fetch' first")
        return 1

    entries = []
    for title in titles:
        data = cache.load(title)
        if data is None:
            logger.warning("Skipping %s (not cached)", title)
            continue
        article = ArticleData.from_dict(data)
        entries.append(ArticleEntry(
            title=title,
            content_length=len(article.html),
        ))

    volumes = balance_volumes(
        entries,
        num_volumes=manifest.volumes.count,
        balance_by=manifest.volumes.balance_by,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for vol in volumes:
        logger.info(
            "Volume %d: %d articles, ~%d chars",
            vol.number, len(vol.articles), vol.total_length,
        )

        parts = [front_matter_html(vol, len(volumes))]
        for entry in vol.articles:
            data = cache.load(entry.title)
            if data is None:
                continue
            article = ArticleData.from_dict(data)
            article_sections = manifest.sections_to_strip(entry.title)
            result = strip_sections(
                article.wikitext, article_sections,
                title=entry.title, html=article.html,
            )
            image_path = _resolve_image_path(cache, article)
            parts.append(render_article_html(
                title=entry.title,
                body_html=result.cleaned_html,
                stripped_sections=result.stripped_sections,
                lead_image_path=image_path,
                callout_config=manifest.callout,
                typography=manifest.typography,
            ))

        volume_html = "\n".join(parts)
        pdf_path = output_dir / f"volume_{vol.number}.pdf"
        render_pdf(volume_html, pdf_path, manifest.volumes)
        logger.info("Volume %d: %s", vol.number, pdf_path)

    return 0


def _resolve_image_path(cache, article) -> str | None:
    """Return absolute path to cached lead image, or None."""
    if article.lead_image_filename:
        img = cache.image_path(article.title, article.lead_image_filename)
        if img.exists():
            return str(img.resolve())
    return None


def _render_articles(manifest, args, cache, titles) -> int:
    from cc_wp_book.fetch import ArticleData
    from cc_wp_book.parse import strip_sections
    from cc_wp_book.render import render_article_html, render_pdf

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    for title in titles:
        data = cache.load(title)
        if data is None:
            logger.error(
                "No cached data for %s — run 'fetch' first", title
            )
            continue

        article = ArticleData.from_dict(data)
        logger.info("Rendering: %s", title)

        article_sections = manifest.sections_to_strip(title)
        result = strip_sections(
            article.wikitext,
            article_sections,
            title=title,
            html=article.html,
        )

        image_path = _resolve_image_path(cache, article)
        page_html = render_article_html(
            title=title,
            body_html=result.cleaned_html,
            stripped_sections=result.stripped_sections,
            lead_image_path=image_path,
            callout_config=manifest.callout,
            typography=manifest.typography,
        )

        slug = title.replace(" ", "_")
        pdf_path = output_dir / f"{slug}.pdf"
        render_pdf(page_html, pdf_path, manifest.volumes)
        logger.info("PDF: %s", pdf_path)

    return 0


def _cmd_validate(manifest, args) -> int:
    from cc_wp_book.render import validate_pdf

    output_dir = args.output_dir
    if not output_dir.exists():
        logger.error("Output directory does not exist: %s", output_dir)
        return 1

    pdfs = sorted(output_dir.glob("*.pdf"))
    if not pdfs:
        logger.error("No PDFs found in %s", output_dir)
        return 1

    all_ok = True
    for pdf_path in pdfs:
        issues = validate_pdf(pdf_path, manifest.volumes)
        if issues:
            for issue in issues:
                logger.error("%s: %s", pdf_path.name, issue)
            all_ok = False
        else:
            logger.info("%s: OK", pdf_path.name)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
