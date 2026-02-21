#!/usr/bin/env python3
"""Build markdown articles into HTML site + index.json + llms.txt."""

import json
import re
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
    CATEGORIES,
)


def extract_key_takeaways(body_md: str) -> list[dict]:
    """Extract Key Takeaways bullet points for FAQ schema."""
    takeaways = []
    in_takeaways = False
    for line in body_md.split("\n"):
        if re.match(r"^##\s+Key Takeaways", line, re.IGNORECASE):
            in_takeaways = True
            continue
        if in_takeaways:
            if line.startswith("## ") or line.startswith("---"):
                break
            match = re.match(r"^[-*]\s+\*\*(.+?)\*\*[:\s]*(.+)", line)
            if match:
                takeaways.append({
                    "name": match.group(1).strip(),
                    "text": match.group(2).strip(),
                })
            else:
                match = re.match(r"^[-*]\s+(.+)", line)
                if match:
                    takeaways.append({
                        "name": "Key point",
                        "text": match.group(1).strip(),
                    })
    return takeaways


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
        "content_type": fm.get("content_type", "brief"),
        "entities": fm.get("entities", []),
        "sentiment": fm.get("sentiment", "neutral"),
        "impact": fm.get("impact", "low"),
        "subcategory": fm.get("subcategory", ""),
        "body_md": body.strip(),
        "html_body": markdown.markdown(body.strip(), extensions=["extra"]),
        "key_takeaways": extract_key_takeaways(body.strip()),
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


def _article_to_json(a: dict) -> dict:
    """Serialize an article dict to JSON-safe format (shared helper)."""
    date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
    return {
        "title": a["title"],
        "slug": a["slug"],
        "date": a["date"],
        "category": a["category"],
        "tags": a["tags"],
        "reporter": a["reporter"],
        "summary": a["summary"],
        "content_type": a["content_type"],
        "entities": a["entities"],
        "sentiment": a["sentiment"],
        "impact": a["impact"],
        "subcategory": a["subcategory"],
        "sources": a["sources"],
        "url_html": f"{SITE_URL}/articles/{date_path}/{a['slug']}.html",
        "url_md": f"{SITE_URL}/articles/{date_path}/{a['slug']}.md",
    }


def build_index_json(articles: list[dict]) -> dict:
    """Build the structured JSON index for agent consumption."""
    dates = [a["date"][:10] for a in articles] if articles else []
    stats = {
        "total_articles": len(articles),
        "categories": sorted(set(a["category"] for a in articles)),
        "date_range": {
            "earliest": min(dates) if dates else None,
            "latest": max(dates) if dates else None,
        },
    }
    return {
        "name": SITE_NAME,
        "url": SITE_URL,
        "description": SITE_DESCRIPTION,
        "updated": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "articles": [_article_to_json(a) for a in articles],
    }


def build_category_json(articles: list[dict]):
    """Build per-category JSON files under /api/category/."""
    api_dir = OUTPUT_DIR / "api" / "category"
    api_dir.mkdir(parents=True, exist_ok=True)

    for category in CATEGORIES:
        filtered = [a for a in articles if a["category"] == category]
        data = {
            "category": category,
            "count": len(filtered),
            "updated": datetime.now(timezone.utc).isoformat(),
            "articles": [_article_to_json(a) for a in filtered],
        }
        (api_dir / f"{category}.json").write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )


def build_today_json(articles: list[dict]):
    """Build /api/today.json with only today's articles (UTC)."""
    api_dir = OUTPUT_DIR / "api"
    api_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filtered = [a for a in articles if a["date"][:10] == today]

    data = {
        "date": today,
        "count": len(filtered),
        "updated": datetime.now(timezone.utc).isoformat(),
        "articles": [_article_to_json(a) for a in filtered],
    }
    (api_dir / "today.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False)
    )


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
        f"- [Today's Articles (JSON)]({SITE_URL}/api/today.json): Articles published today (UTC)",
        f"- [Category API]({SITE_URL}/api/category/): Per-category JSON endpoints (markets, macro, crypto, etc.)",
        f"- [Versioned API]({SITE_URL}/v1/articles.json): Stable v1 endpoint for all articles",
        f"- [RSS Feed]({SITE_URL}/feed.xml): Standard RSS 2.0 feed",
        f"- [Full Content]({SITE_URL}/llms-full.txt): Complete article text for LLM consumption",
        "",
        "## Recent Articles",
        "",
    ]
    for a in articles[:20]:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        md_url = f"{SITE_URL}/articles/{date_path}/{a['slug']}.md"
        lines.append(f"- [{a['title']}]({md_url}): {a['summary'][:120]}")

    return "\n".join(lines) + "\n"


def build_sitemap(articles: list[dict]) -> str:
    """Build sitemap.xml for search engine discovery."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url>',
        f'    <loc>{SITE_URL}/</loc>',
        '    <changefreq>hourly</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>',
    ]
    for a in articles:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        lines.extend([
            '  <url>',
            f'    <loc>{SITE_URL}/articles/{date_path}/{a["slug"]}.html</loc>',
            f'    <lastmod>{a["date"][:10]}</lastmod>',
            '    <changefreq>monthly</changefreq>',
            '    <priority>0.8</priority>',
            '  </url>',
        ])
    lines.append('</urlset>')
    return "\n".join(lines)


def build_llms_full_txt(articles: list[dict]) -> str:
    """Build llms-full.txt with complete article content."""
    lines = [
        f"# {SITE_NAME} - Full Content",
        "",
        f"> {SITE_DESCRIPTION}",
        "",
    ]
    for a in articles:
        lines.extend([
            f"## {a['title']}",
            "",
            f"Date: {a['date'][:10]}",
            f"Category: {a['category']}",
            f"Tags: {', '.join(a['tags'])}",
            f"Reporter: {a['reporter']}",
            "",
            a['body_md'],
            "",
            "---",
            "",
        ])
    return "\n".join(lines)


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

    # Build per-category JSON
    build_category_json(articles)

    # Build today.json
    build_today_json(articles)

    # Build v1/articles.json (versioned API)
    v1_dir = OUTPUT_DIR / "v1"
    v1_dir.mkdir(parents=True, exist_ok=True)
    (v1_dir / "articles.json").write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False)
    )

    # Build llms.txt
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(articles))

    # Build feed.xml
    feed_tmpl = env.get_template("feed.xml")
    (OUTPUT_DIR / "feed.xml").write_text(
        feed_tmpl.render(**ctx, articles=articles[:50])
    )

    # Build sitemap.xml
    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap(articles))

    # Build llms-full.txt
    (OUTPUT_DIR / "llms-full.txt").write_text(build_llms_full_txt(articles))

    # Build .well-known/ai-plugin.json
    well_known_dir = OUTPUT_DIR / ".well-known"
    well_known_dir.mkdir(exist_ok=True)
    ai_plugin = {
        "schema_version": "v1",
        "name_for_human": SITE_NAME,
        "name_for_model": "molt_street_journal",
        "description_for_human": SITE_DESCRIPTION,
        "description_for_model": "Financial news API providing articles about markets, macroeconomics, crypto, real estate, tech, commodities, and international news. Articles include structured metadata (entities, sentiment, impact), tags, sources, and are available in HTML, JSON, and Markdown formats.",
        "api": {
            "type": "openapi",
            "url": f"{SITE_URL}/index.json",
        },
        "endpoints": {
            "articles_json": f"{SITE_URL}/index.json",
            "articles_v1": f"{SITE_URL}/v1/articles.json",
            "today": f"{SITE_URL}/api/today.json",
            "category": f"{SITE_URL}/api/category/{{category}}.json",
            "articles_rss": f"{SITE_URL}/feed.xml",
            "llms_txt": f"{SITE_URL}/llms.txt",
            "llms_full_txt": f"{SITE_URL}/llms-full.txt",
            "sitemap": f"{SITE_URL}/sitemap.xml",
        },
    }
    (well_known_dir / "ai-plugin.json").write_text(
        json.dumps(ai_plugin, indent=2, ensure_ascii=False)
    )

    # Build robots.txt
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
"""
    (OUTPUT_DIR / "robots.txt").write_text(robots)

    # CNAME for GitHub Pages
    (OUTPUT_DIR / "CNAME").write_text("moltstreetjournal.com\n")

    print(f"Built site to {OUTPUT_DIR}")
    print(f"  index.html, index.json, llms.txt, llms-full.txt, feed.xml, sitemap.xml, robots.txt")
    print(f"  api/today.json, api/category/*.json, v1/articles.json")
    print(f"  {len(articles)} article(s)")


if __name__ == "__main__":
    build()
