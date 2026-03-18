# cc-wp-book

An open-source pipeline that transforms Wikipedia's [1,000 Vital Articles](https://en.wikipedia.org/wiki/Wikipedia:Vital_articles) into a set of print-ready PDF encyclopedia volumes.

## Purpose

This project produces a curated, print-formatted encyclopedia drawn entirely from Wikipedia's highest-priority articles. **All markup from sales goes to the Wikimedia Foundation.**

Each article explicitly directs readers back to Wikipedia for content that was removed for print formatting, with QR codes and direct URLs. The goal is to complement Wikipedia — not compete with it — by offering a physical artifact that celebrates the depth and quality of the encyclopedia's core content.

## How It Works

The pipeline has five stages:

1. **Fetch** — Retrieves the Vital Articles list and each article's wikitext, lead image, and metadata via the Wikipedia/Wikimedia APIs.

2. **Parse** — Strips configurable sections (References, See Also, External Links, etc.) from each article. The exact sections removed are controlled by `manifest.yaml` and documented per-article in a callout box.

3. **Transform** — Converts cleaned wikitext to styled HTML, preserving infoboxes and lead images. Each article includes a callout box listing stripped sections with a QR code linking to the full Wikipedia article.

4. **Render** — Produces print-ready PDFs via WeasyPrint, meeting IngramSpark's technical specifications (trim size, bleed, embedded fonts, 300 DPI images).

5. **Assemble** — Distributes articles across 4–5 hardcover volumes balanced by content length, with front matter including full Creative Commons attribution and methodology disclosure.

## Methodology & Transparency

Every aspect of the editorial process is documented and reproducible:

- **`manifest.yaml`** controls exactly which sections are stripped and why. Per-article overrides are supported.
- **Every article** includes a callout box listing the removed sections and a link to the complete article on Wikipedia.
- **The pipeline is open source** — anyone can audit, reproduce, or improve the output.
- **No original content is added.** The text is Wikipedia's, reformatted for print.

This transparency is by design. We want the Wikimedia Foundation and community to be able to evaluate exactly what this project does and how it does it.

## Attribution & License

The article content is derived from Wikipedia and is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Each volume's front matter includes:

- Full Creative Commons attribution
- Acknowledgment of Wikipedia's contributors
- Methodology disclosure explaining what was modified and why
- A note that all markup from sales goes to the Wikimedia Foundation

The pipeline code itself is MIT licensed.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Fetch the vital articles list
cc-wp-book fetch --list-only

# Fetch draft articles (5 representative articles)
cc-wp-book fetch --draft

# Run tests
pytest
```

## Configuration

All pipeline behavior is controlled by `manifest.yaml`:

- **`strip_sections`** — Headers to remove from every article
- **`optional_strip_sections`** — Headers that can be toggled on/off globally
- **`article_overrides`** — Per-article additions or exceptions to stripping rules
- **`volumes`** — Number of volumes, trim size, bleed
- **`typography`** — Font choices, body size, line height
- **`images`** — Target DPI, max width
- **`api`** — User agent, rate limiting, retry settings
- **`draft_articles`** — Articles used for CI preview rendering

## CI Pipeline

Every pull request:

1. Runs the full test suite
2. Lints with ruff
3. Fetches and renders 5 draft articles as a preview artifact
4. Validates PDF output against print specifications

## Project Structure

```
src/cc_wp_book/
├── cli.py          # Command-line interface
├── config.py       # Manifest loading and validation
├── fetch.py        # Wikipedia API client
├── parse.py        # Section stripping
├── transform.py    # Wikitext → HTML conversion
├── callout.py      # Stripped-sections callout box + QR
├── render.py       # HTML → PDF via WeasyPrint
└── assemble.py     # Volume balancing and front matter
```
