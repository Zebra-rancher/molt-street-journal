#!/usr/bin/env python3
"""Build markdown articles into HTML site + index.json + llms.txt."""

import json
import shutil
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader

from config import (
    CONTENT_DIR, OUTPUT_DIR, TEMPLATES_DIR, STATIC_DIR,
    SITE_NAME, SITE_URL, SITE_DESCRIPTION, SITE_LANGUAGE,
)


def parse_article(path: Path) -> dict:
    """Parse a markdown file with YAML frontmatter into an article dict."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None

    _, fm_raw, body = text.split("---", 2)
    fm = yaml.safe_load(fm_raw)

    date_str = str(fm["date"])
    if isinstance(fm["date"], datetime):
        dt = fm["date"]
    else:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

    return {
        "title": fm["title"],
        "slug": fm["slug"],
        "date": dt.isoformat(),
        "rfc822_date": format_datetime(dt),
        "sources": fm.get("sources", []),
        "tags": fm.get("tags", []),
        "category": fm.get("category", "general"),
        "reporter": fm.get("reporter", "unknown"),
        "summary": fm.get("summary", "").strip(),
        "body_md": body.strip(),
        "html_body": markdown.markdown(body.strip(), extensions=["extra"]),
        "source_path": path,
    }


def load_articles() -> list[dict]:
    """Load all articles from content directory, sorted newest first."""
    articles = []
    for md_file in CONTENT_DIR.rglob("*.md"):
        article = parse_article(md_file)
        if article:
            articles.append(article)
    articles.sort(key=lambda a: a["date"], reverse=True)
    return articles


def build_index_json(articles: list[dict]) -> dict:
    """Build the structured JSON index for agent consumption."""
    return {
        "name": SITE_NAME,
        "url": SITE_URL,
        "description": SITE_DESCRIPTION,
        "updated": datetime.now(timezone.utc).isoformat(),
        "articles": [
            {
                "title": a["title"],
                "slug": a["slug"],
                "date": a["date"],
                "category": a["category"],
                "tags": a["tags"],
                "reporter": a["reporter"],
                "summary": a["summary"],
                "sources": a["sources"],
                "url_html": f"{SITE_URL}/articles/{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}/{a['slug']}.html",
                "url_md": f"{SITE_URL}/articles/{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}/{a['slug']}.md",
            }
            for a in articles
        ],
    }


def build_llms_txt(articles: list[dict]) -> str:
    """Build llms.txt for agent discovery."""
    lines = [
        f"# {SITE_NAME}",
        "",
        f"> {SITE_DESCRIPTION}",
        "",
        "## API",
        "",
        f"- [Article Index (JSON)]({SITE_URL}/index.json): Structured index of all articles with metadata and summaries",
        f"- [RSS Feed]({SITE_URL}/feed.xml): Standard RSS 2.0 feed",
        "",
        "## Recent Articles",
        "",
    ]
    for a in articles[:20]:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        md_url = f"{SITE_URL}/articles/{date_path}/{a['slug']}.md"
        lines.append(f"- [{a['title']}]({md_url}): {a['summary'][:120]}")

    return "\n".join(lines) + "\n"


def build():
    """Run the full build."""
    # Clean output
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    # Copy static files
    if STATIC_DIR.exists():
        for f in STATIC_DIR.iterdir():
            shutil.copy2(f, OUTPUT_DIR / f.name)

    # Load articles
    articles = load_articles()
    print(f"Found {len(articles)} articles")

    # Set up Jinja
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    ctx = {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "site_description": SITE_DESCRIPTION,
        "site_language": SITE_LANGUAGE,
        "base_url": "",  # relative paths for local preview
    }

    # Build index.html
    tmpl = env.get_template("index.html")
    (OUTPUT_DIR / "index.html").write_text(tmpl.render(**ctx, articles=articles))

    # Build each article HTML + copy raw .md
    tmpl = env.get_template("article.html")
    for a in articles:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        article_dir = OUTPUT_DIR / "articles" / date_path
        article_dir.mkdir(parents=True, exist_ok=True)

        html = tmpl.render(**ctx, article=a)
        (article_dir / f"{a['slug']}.html").write_text(html)

        # Copy raw markdown for agent access
        shutil.copy2(a["source_path"], article_dir / f"{a['slug']}.md")

    # Build index.json
    index_data = build_index_json(articles)
    (OUTPUT_DIR / "index.json").write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False)
    )

    # Build llms.txt
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(articles))

    # Build feed.xml
    feed_tmpl = env.get_template("feed.xml")
    (OUTPUT_DIR / "feed.xml").write_text(
        feed_tmpl.render(**ctx, articles=articles[:50])
    )

    # Build robots.txt
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/index.json
"""
    (OUTPUT_DIR / "robots.txt").write_text(robots)

    # CNAME for GitHub Pages
    (OUTPUT_DIR / "CNAME").write_text("moltstreetjournal.com\n")

    print(f"Built site to {OUTPUT_DIR}")
    print(f"  index.html, index.json, llms.txt, feed.xml, robots.txt")
    print(f"  {len(articles)} article(s)")


if __name__ == "__main__":
    build()
