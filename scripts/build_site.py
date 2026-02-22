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
    CATEGORIES, BRIEFINGS_DIR,
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


def load_latest_briefing() -> dict | None:
    """Load the most recent briefing from content/briefings/."""
    if not BRIEFINGS_DIR.exists():
        return None
    files = sorted(BRIEFINGS_DIR.glob("*.md"), reverse=True)
    if not files:
        return None
    path = files[0]
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    _, fm_raw, body = text.split("---", 2)
    fm = yaml.safe_load(fm_raw)
    fm["body_md"] = body.strip()
    fm["html_body"] = markdown.markdown(body.strip(), extensions=["extra"])
    return fm


def find_related_articles(target: dict, all_articles: list[dict], max_results: int = 5) -> list[dict]:
    """Find related articles using tag and entity overlap (Jaccard similarity)."""
    target_tags = set(target.get("tags", []))
    target_entities = {e["name"].lower() for e in target.get("entities", [])}
    scored = []
    for a in all_articles:
        if a["slug"] == target["slug"]:
            continue
        a_tags = set(a.get("tags", []))
        a_entities = {e["name"].lower() for e in a.get("entities", [])}
        # Jaccard similarity on tags
        tag_union = target_tags | a_tags
        tag_sim = len(target_tags & a_tags) / len(tag_union) if tag_union else 0
        # Entity overlap (weighted higher)
        ent_union = target_entities | a_entities
        ent_sim = len(target_entities & a_entities) / len(ent_union) if ent_union else 0
        # Same category bonus
        cat_bonus = 0.1 if a["category"] == target["category"] else 0
        score = tag_sim + (ent_sim * 1.5) + cat_bonus
        if score > 0.05:
            scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:max_results]]


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


def build_briefing_json(briefing: dict | None):
    """Build /api/briefing.json and /api/briefing/today.json."""
    api_dir = OUTPUT_DIR / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    briefing_dir = api_dir / "briefing"
    briefing_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if briefing:
        data = {
            "date": briefing.get("date", today),
            "generated_at": briefing.get("generated_at", ""),
            "available": True,
            "article_count": briefing.get("article_count", 0),
            "overall_sentiment": briefing.get("overall_sentiment", "neutral"),
            "confidence": briefing.get("confidence", "low"),
            "headline": briefing.get("headline", ""),
            "category_breakdown": briefing.get("category_breakdown", {}),
            "sentiment_breakdown": briefing.get("sentiment_breakdown", {}),
            "urls": {
                "markdown": f"{SITE_URL}/briefings/{briefing.get('date', today)}.md",
                "html": f"{SITE_URL}/",
            },
        }
    else:
        data = {
            "date": today,
            "available": False,
            "message": "No briefing available for today.",
        }

    (api_dir / "briefing.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (briefing_dir / "today.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))


def build_llms_txt(articles: list[dict], briefing: dict | None = None) -> str:
    """Build llms.txt for agent discovery."""
    lines = [
        f"# {SITE_NAME}",
        "",
        f"> {SITE_DESCRIPTION}",
        "",
        "## About",
        "",
        f"{SITE_NAME} is an AI-powered financial news service that publishes articles every 2 hours.",
        "Articles are generated from verified RSS sources and include structured metadata.",
        "Content is available in HTML, JSON, Markdown, and plain text formats.",
        f"Update frequency: Every 2 hours. Current article count: {len(articles)}.",
        "",
        "## Usage Guidelines",
        "",
        f"- Attribution: Please cite '{SITE_NAME} (moltstreetjournal.com)' when referencing content",
        "- Data freshness: Articles are timestamped in ISO 8601 format",
        "- Rate limits: No rate limits on static endpoints",
        "- Preferred format for agents: JSON API or Markdown files",
        "",
    ]

    if briefing:
        lines.extend([
            "## Daily Market Briefing",
            "",
            f"**{briefing.get('headline', '')}**",
            f"Sentiment: {briefing.get('overall_sentiment', 'neutral')} | Articles: {briefing.get('article_count', 0)}",
            f"- [Briefing JSON]({SITE_URL}/api/briefing.json)",
            f"- [Briefing Markdown]({SITE_URL}/briefings/{briefing.get('date', '')}.md)",
            "",
        ])

    lines.extend([
        "## API Endpoints",
        "",
        f"- [Article Index (JSON)]({SITE_URL}/index.json): Structured index of all articles with metadata and summaries",
        f"- [Today's Articles (JSON)]({SITE_URL}/api/today.json): Articles published today (UTC)",
        f"- [Category API]({SITE_URL}/api/category/): Per-category JSON endpoints",
        f"- [Versioned API]({SITE_URL}/v1/articles.json): Stable v1 endpoint for all articles",
        f"- [RSS Feed]({SITE_URL}/feed.xml): Standard RSS 2.0 feed",
        f"- [Full Content]({SITE_URL}/llms-full.txt): Complete article text for LLM consumption",
        "",
        "## Categories",
        "",
    ])
    for cat in CATEGORIES:
        count = sum(1 for a in articles if a["category"] == cat)
        lines.append(f"- [{cat}]({SITE_URL}/api/category/{cat}.json): {count} articles")
    lines.extend([
        "",
        "## Article Schema",
        "",
        "Each article in the JSON API includes:",
        "- title, slug, date (ISO 8601)",
        "- category, subcategory, tags",
        "- entities (name + type: organization, person, index)",
        "- sentiment (neutral, bullish, bearish)",
        "- impact (low, medium, high)",
        "- summary, sources with URLs",
        "- Available as: HTML (.html), JSON (via API), and raw Markdown (.md)",
        "",
        "## Recent Articles",
        "",
    ])
    for a in articles[:20]:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        md_url = f"{SITE_URL}/articles/{date_path}/{a['slug']}.md"
        lines.append(f"- [{a['title']}]({md_url}): {a['summary'][:120]}")

    return "\n".join(lines) + "\n"


def build_sitemap(articles: list[dict], total_pages: int = 1) -> str:
    """Build sitemap.xml for search engine discovery."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        '  <url>',
        f'    <loc>{SITE_URL}/</loc>',
        '    <changefreq>hourly</changefreq>',
        '    <priority>1.0</priority>',
        '  </url>',
        '  <url>',
        f'    <loc>{SITE_URL}/about.html</loc>',
        '    <changefreq>monthly</changefreq>',
        '    <priority>0.5</priority>',
        '  </url>',
    ]
    # Category pages
    for cat in CATEGORIES:
        lines.extend([
            '  <url>',
            f'    <loc>{SITE_URL}/category/{cat}.html</loc>',
            '    <changefreq>hourly</changefreq>',
            '    <priority>0.9</priority>',
            '  </url>',
        ])
    # Paginated pages
    for p in range(2, total_pages + 1):
        lines.extend([
            '  <url>',
            f'    <loc>{SITE_URL}/page/{p}.html</loc>',
            '    <changefreq>daily</changefreq>',
            '    <priority>0.6</priority>',
            '  </url>',
        ])
    # Articles
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


ARTICLES_PER_PAGE = 25


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
    briefing = load_latest_briefing()
    print(f"Found {len(articles)} articles")

    # Set up Jinja
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)
    ctx = {
        "site_name": SITE_NAME,
        "site_url": SITE_URL,
        "site_description": SITE_DESCRIPTION,
        "site_language": SITE_LANGUAGE,
        "base_url": "",  # relative paths for local preview
        "categories": CATEGORIES,
    }

    # --- Paginated homepage ---
    total_pages = max(1, -(-len(articles) // ARTICLES_PER_PAGE))  # ceiling division
    index_tmpl = env.get_template("index.html")

    # Page 1 = index.html
    page1_articles = articles[:ARTICLES_PER_PAGE]
    (OUTPUT_DIR / "index.html").write_text(index_tmpl.render(
        **ctx,
        articles=page1_articles,
        briefing=briefing,
        current_page=1,
        total_pages=total_pages,
        has_prev=False,
        has_next=total_pages > 1,
    ))

    # Pages 2..N
    if total_pages > 1:
        page_dir = OUTPUT_DIR / "page"
        page_dir.mkdir(parents=True, exist_ok=True)
        for page_num in range(2, total_pages + 1):
            start = (page_num - 1) * ARTICLES_PER_PAGE
            end = start + ARTICLES_PER_PAGE
            page_articles = articles[start:end]
            (page_dir / f"{page_num}.html").write_text(index_tmpl.render(
                **ctx,
                articles=page_articles,
                briefing=None,  # only show briefing on page 1
                current_page=page_num,
                total_pages=total_pages,
                has_prev=True,
                has_next=page_num < total_pages,
            ))
    print(f"  Built {total_pages} index page(s)")

    # --- Category HTML pages ---
    try:
        cat_tmpl = env.get_template("category.html")
        cat_dir = OUTPUT_DIR / "category"
        cat_dir.mkdir(parents=True, exist_ok=True)
        for category in CATEGORIES:
            cat_articles = [a for a in articles if a["category"] == category]
            (cat_dir / f"{category}.html").write_text(cat_tmpl.render(
                **ctx,
                category=category,
                articles=cat_articles,
                article_count=len(cat_articles),
            ))
        print(f"  Built {len(CATEGORIES)} category pages")
    except Exception as e:
        print(f"  Warning: category pages skipped: {e}")

    # --- Article HTML pages with related articles ---
    article_tmpl = env.get_template("article.html")
    for a in articles:
        date_path = f"{a['date'][:4]}/{a['date'][5:7]}/{a['date'][8:10]}"
        article_dir = OUTPUT_DIR / "articles" / date_path
        article_dir.mkdir(parents=True, exist_ok=True)

        related = find_related_articles(a, articles)
        html = article_tmpl.render(**ctx, article=a, related_articles=related)
        (article_dir / f"{a['slug']}.html").write_text(html)

        # Copy raw markdown for agent access
        shutil.copy2(a["source_path"], article_dir / f"{a['slug']}.md")

    # --- About page ---
    try:
        about_tmpl = env.get_template("about.html")
        (OUTPUT_DIR / "about.html").write_text(about_tmpl.render(**ctx))
    except Exception:
        print("  Warning: about.html template not found, skipping")

    # --- 404 page ---
    try:
        err_tmpl = env.get_template("404.html")
        (OUTPUT_DIR / "404.html").write_text(err_tmpl.render(**ctx, recent_articles=articles[:5]))
    except Exception:
        print("  Warning: 404.html template not found, skipping")

    # --- JSON APIs ---
    index_data = build_index_json(articles)
    (OUTPUT_DIR / "index.json").write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False)
    )
    build_category_json(articles)
    build_today_json(articles)
    build_briefing_json(briefing)

    v1_dir = OUTPUT_DIR / "v1"
    v1_dir.mkdir(parents=True, exist_ok=True)
    (v1_dir / "articles.json").write_text(
        json.dumps(index_data, indent=2, ensure_ascii=False)
    )

    # --- llms.txt ---
    (OUTPUT_DIR / "llms.txt").write_text(build_llms_txt(articles, briefing))

    # --- feed.xml ---
    feed_tmpl = env.get_template("feed.xml")
    (OUTPUT_DIR / "feed.xml").write_text(
        feed_tmpl.render(**ctx, articles=articles[:50])
    )

    # --- sitemap.xml ---
    (OUTPUT_DIR / "sitemap.xml").write_text(build_sitemap(articles, total_pages))

    # --- llms-full.txt ---
    (OUTPUT_DIR / "llms-full.txt").write_text(build_llms_full_txt(articles))

    # --- Copy briefing markdown files ---
    if BRIEFINGS_DIR.exists():
        briefings_out = OUTPUT_DIR / "briefings"
        briefings_out.mkdir(parents=True, exist_ok=True)
        for bf in BRIEFINGS_DIR.glob("*.md"):
            shutil.copy2(bf, briefings_out / bf.name)

    # --- .well-known/ ---
    well_known_dir = OUTPUT_DIR / ".well-known"
    well_known_dir.mkdir(exist_ok=True)

    # ai-plugin.json (fixed: type changed from openapi to json, added logo/contact)
    ai_plugin = {
        "schema_version": "v1",
        "name_for_human": SITE_NAME,
        "name_for_model": "molt_street_journal",
        "description_for_human": SITE_DESCRIPTION,
        "description_for_model": "Financial news API providing articles about markets, macroeconomics, crypto, real estate, tech, commodities, and international news. Articles include structured metadata (entities, sentiment, impact), tags, sources, and are available in HTML, JSON, and Markdown formats.",
        "logo_url": f"{SITE_URL}/og-default.png",
        "contact_email": "hello@moltstreetjournal.com",
        "legal_info_url": f"{SITE_URL}/about.html",
        "api": {
            "type": "json",
            "url": f"{SITE_URL}/v1/articles.json",
            "documentation": f"{SITE_URL}/llms.txt",
        },
        "endpoints": {
            "articles_json": f"{SITE_URL}/index.json",
            "articles_v1": f"{SITE_URL}/v1/articles.json",
            "today": f"{SITE_URL}/api/today.json",
            "category": f"{SITE_URL}/api/category/{{category}}.json",
            "articles_rss": f"{SITE_URL}/feed.xml",
            "llms_txt": f"{SITE_URL}/llms.txt",
            "llms_full_txt": f"{SITE_URL}/llms-full.txt",
            "briefing": f"{SITE_URL}/api/briefing.json",
            "briefing_today": f"{SITE_URL}/api/briefing/today.json",
            "sitemap": f"{SITE_URL}/sitemap.xml",
        },
    }
    (well_known_dir / "ai-plugin.json").write_text(
        json.dumps(ai_plugin, indent=2, ensure_ascii=False)
    )

    # ai.json (agent discovery standard)
    ai_json = {
        "version": "1.0",
        "name": SITE_NAME,
        "description": SITE_DESCRIPTION,
        "url": SITE_URL,
        "robots": f"{SITE_URL}/robots.txt",
        "sitemap": f"{SITE_URL}/sitemap.xml",
        "llms_txt": f"{SITE_URL}/llms.txt",
        "llms_full_txt": f"{SITE_URL}/llms-full.txt",
        "api": {
            "articles": f"{SITE_URL}/v1/articles.json",
            "today": f"{SITE_URL}/api/today.json",
            "categories": f"{SITE_URL}/api/category/{{category}}.json",
            "briefing": f"{SITE_URL}/api/briefing.json",
            "rss": f"{SITE_URL}/feed.xml",
        },
        "contact": "hello@moltstreetjournal.com",
    }
    (well_known_dir / "ai.json").write_text(
        json.dumps(ai_json, indent=2, ensure_ascii=False)
    )

    # --- robots.txt (expanded for AI crawlers) ---
    robots = f"""User-agent: *
Allow: /

# AI Crawlers - explicitly welcome
User-agent: GPTBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Applebot-Extended
Allow: /

Sitemap: {SITE_URL}/sitemap.xml

# Agent discovery
# llms.txt: {SITE_URL}/llms.txt
# llms-full.txt: {SITE_URL}/llms-full.txt
"""
    (OUTPUT_DIR / "robots.txt").write_text(robots)

    # CNAME
    (OUTPUT_DIR / "CNAME").write_text("moltstreetjournal.com\n")

    print(f"Built site to {OUTPUT_DIR}")
    print(f"  {len(articles)} articles, {len(CATEGORIES)} category pages, {total_pages} index page(s)")
    print(f"  index.json, llms.txt, llms-full.txt, feed.xml, sitemap.xml, robots.txt")
    print(f"  api/today.json, api/category/*.json, v1/articles.json, api/briefing.json")
    print(f"  .well-known/ai-plugin.json, .well-known/ai.json")
    print(f"  about.html, 404.html")


if __name__ == "__main__":
    build()
