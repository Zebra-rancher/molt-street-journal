#!/usr/bin/env python3
"""Fetch financial news from RSS feeds and save raw items as JSON."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml

from config import FEEDS_FILE, RSS_RAW_DIR, PROCESSED_FILE


def load_processed() -> set:
    """Load set of already-processed item IDs."""
    if PROCESSED_FILE.exists():
        return set(json.loads(PROCESSED_FILE.read_text()))
    return set()


def save_processed(ids: set):
    """Persist processed item IDs."""
    PROCESSED_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROCESSED_FILE.write_text(json.dumps(sorted(ids)))


def item_id(entry: dict, feed_name: str) -> str:
    """Generate a stable ID for an RSS entry."""
    key = entry.get("id") or entry.get("link") or entry.get("title", "")
    return hashlib.sha256(f"{feed_name}:{key}".encode()).hexdigest()[:16]


def fetch_feeds():
    """Fetch all configured RSS feeds and save new items."""
    feeds_config = yaml.safe_load(FEEDS_FILE.read_text())
    processed = load_processed()
    new_items = []

    for feed_cfg in feeds_config["feeds"]:
        name = feed_cfg["name"]
        url = feed_cfg["url"]
        category = feed_cfg.get("category", "general")

        print(f"Fetching {name}...")
        try:
            d = feedparser.parse(url)
        except Exception as e:
            print(f"  Error fetching {name}: {e}")
            continue

        count = 0
        for entry in d.entries[:10]:  # cap per feed
            iid = item_id(entry, name)
            if iid in processed:
                continue

            published = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).isoformat()

            item = {
                "id": iid,
                "feed": name,
                "category": category,
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", ""),
                "summary": entry.get("summary", "").strip()[:500],
                "published": published,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
            }

            new_items.append(item)
            processed.add(iid)
            count += 1

        print(f"  {count} new items from {name}")

    # Save new items
    if new_items:
        RSS_RAW_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        outfile = RSS_RAW_DIR / f"batch_{timestamp}.json"
        outfile.write_text(json.dumps(new_items, indent=2, ensure_ascii=False))
        print(f"\nSaved {len(new_items)} items to {outfile}")
    else:
        print("\nNo new items found.")

    save_processed(processed)
    return new_items


if __name__ == "__main__":
    fetch_feeds()
