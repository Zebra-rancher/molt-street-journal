#!/usr/bin/env python3
"""Generate a daily market briefing from today's articles using Gemini."""

import os
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from google import genai
from google.genai import types

from config import CONTENT_DIR, BRIEFINGS_DIR, GEMINI_MODEL

SYSTEM_PROMPT = """You are an AI financial analyst for the Molt Street Journal. Synthesize today's articles into a structured daily market briefing.

Rules:
- Neutral, factual tone — no speculation or opinion
- Summarize trends, don't repeat individual articles
- Highlight cross-cutting themes and sector connections
- Be concise but comprehensive
"""


def collect_today_articles() -> list[dict]:
    """Load frontmatter from all of today's articles."""
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    today_dir = CONTENT_DIR / today
    if not today_dir.exists():
        return []

    articles = []
    for md_file in today_dir.glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        _, fm_raw, _ = text.split("---", 2)
        fm = yaml.safe_load(fm_raw)
        articles.append({
            "title": fm.get("title", ""),
            "category": fm.get("category", "general"),
            "sentiment": fm.get("sentiment", "neutral"),
            "impact": fm.get("impact", "low"),
            "summary": fm.get("summary", ""),
            "entities": fm.get("entities", []),
        })
    return articles


def build_prompt(articles: list[dict]) -> str:
    """Build the Gemini prompt from today's articles."""
    # Group by category
    by_category = {}
    for a in articles:
        by_category.setdefault(a["category"], []).append(a)

    # Sentiment breakdown
    sentiments = {}
    for a in articles:
        s = a["sentiment"]
        sentiments[s] = sentiments.get(s, 0) + 1

    lines = [
        f"Today's date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        f"Total articles: {len(articles)}",
        f"Categories: {', '.join(f'{k} ({len(v)})' for k, v in sorted(by_category.items()))}",
        f"Sentiment breakdown: {', '.join(f'{k}: {v}' for k, v in sorted(sentiments.items()))}",
        "",
        "Articles by category:",
        "",
    ]

    for category, cat_articles in sorted(by_category.items()):
        lines.append(f"### {category.upper()}")
        for a in cat_articles:
            entities_str = ", ".join(
                e["name"] if isinstance(e, dict) else str(e)
                for e in a["entities"]
            ) if a["entities"] else "none"
            lines.append(
                f"- [{a['sentiment']}/{a['impact']}] {a['title']}"
                f"\n  Summary: {a['summary']}"
                f"\n  Entities: {entities_str}"
            )
        lines.append("")

    lines.extend([
        "Generate a daily market briefing with these exact sections.",
        "Each section label must appear on its own line followed by a colon and the value.",
        "For multi-line sections, put the label:value on one line, then content below.",
        "",
        "OVERALL_SENTIMENT: <bullish|bearish|neutral|mixed>",
        "CONFIDENCE: <low|medium|high>",
        "HEADLINE: <single-line headline summarizing today's market>",
        "",
        "MARKET_OVERVIEW:",
        "<2-3 paragraph overview of today's market activity>",
        "",
        "KEY_MOVERS:",
        "<bullet list of stocks/assets/sectors with notable movement>",
        "",
        "SECTOR_HIGHLIGHTS:",
        "<bullet list of sector-specific developments>",
        "",
        "MACRO_SIGNALS:",
        "<bullet list of macroeconomic indicators and policy signals>",
        "",
        "WATCH_LIST:",
        "<bullet list of things to watch tomorrow/this week>",
        "",
        "AGENT_NOTES:",
        "<structured notes useful for AI agents: key data points, thresholds, dates>",
    ])

    return "\n".join(lines)


def generate_briefing(client, articles: list[dict]) -> str | None:
    """Call Gemini to generate the daily briefing."""
    prompt = build_prompt(articles)

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    max_output_tokens=2048,
                ),
            )
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) and attempt < 2:
                wait = 45 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
                continue
            print(f"  API error: {e}")
            return None

    return None


def save_briefing(text: str, articles: list[dict]):
    """Parse Gemini response and save as markdown with YAML frontmatter."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Parse structured fields
    lines = text.split("\n")
    fields = {}
    current_section = None
    section_lines = {}

    single_line_fields = {"OVERALL_SENTIMENT", "CONFIDENCE", "HEADLINE"}
    multi_line_fields = {
        "MARKET_OVERVIEW", "KEY_MOVERS", "SECTOR_HIGHLIGHTS",
        "MACRO_SIGNALS", "WATCH_LIST", "AGENT_NOTES",
    }
    all_fields = single_line_fields | multi_line_fields

    for line in lines:
        # Check if this line starts a new section
        matched = False
        for field in all_fields:
            if line.startswith(f"{field}:"):
                value = line[len(field) + 1:].strip()
                if field in single_line_fields:
                    fields[field] = value
                else:
                    current_section = field
                    section_lines[field] = []
                    if value:
                        section_lines[field].append(value)
                matched = True
                break

        if not matched and current_section:
            section_lines[current_section].append(line)

    # Clean up section content
    for key, content_lines in section_lines.items():
        fields[key] = "\n".join(content_lines).strip()

    # Category breakdown
    by_category = {}
    for a in articles:
        cat = a["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    # Sentiment breakdown
    sentiments = {}
    for a in articles:
        s = a["sentiment"]
        sentiments[s] = sentiments.get(s, 0) + 1

    # Build frontmatter
    frontmatter = {
        "date": today,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "overall_sentiment": fields.get("OVERALL_SENTIMENT", "neutral").lower(),
        "confidence": fields.get("CONFIDENCE", "low").lower(),
        "headline": fields.get("HEADLINE", "Daily Market Briefing"),
        "category_breakdown": by_category,
        "sentiment_breakdown": sentiments,
        "generator": GEMINI_MODEL,
    }

    # Build markdown body
    body_parts = []
    section_titles = {
        "MARKET_OVERVIEW": "Market Overview",
        "KEY_MOVERS": "Key Movers",
        "SECTOR_HIGHLIGHTS": "Sector Highlights",
        "MACRO_SIGNALS": "Macro Signals",
        "WATCH_LIST": "Watch List",
        "AGENT_NOTES": "Agent Notes",
    }
    for key, title in section_titles.items():
        content = fields.get(key, "")
        if content:
            body_parts.append(f"## {title}\n\n{content}")

    body = "\n\n".join(body_parts)

    # Write file
    BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = BRIEFINGS_DIR / f"{today}.md"

    content = (
        "---\n"
        + yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        + "---\n\n"
        + body
        + "\n"
    )
    path.write_text(content, encoding="utf-8")
    print(f"Saved briefing: {path}")


def run():
    """Generate the daily market briefing."""
    articles = collect_today_articles()
    if not articles:
        print("No articles today — skipping briefing.")
        return

    print(f"Generating briefing from {len(articles)} articles...")

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Error: Set GOOGLE_API_KEY or GEMINI_API_KEY environment variable")
        return

    client = genai.Client(api_key=api_key)
    result = generate_briefing(client, articles)
    if not result:
        print("Briefing generation failed.")
        return

    save_briefing(result, articles)


if __name__ == "__main__":
    run()
