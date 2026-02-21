from pathlib import Path

# Paths
ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "articles"
DATA_DIR = ROOT / "data"
RSS_RAW_DIR = DATA_DIR / "rss_raw"
OUTPUT_DIR = ROOT / "output"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
FEEDS_FILE = ROOT / "feeds.yml"
PROCESSED_FILE = DATA_DIR / "processed.json"

# Site
SITE_NAME = "Molt Street Journal"
SITE_URL = "https://moltstreetjournal.com"
SITE_DESCRIPTION = "Financial news for humans and agents"
SITE_LANGUAGE = "en"

# LLM
HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_ARTICLES_PER_RUN = 50
ARTICLE_MIN_WORDS = 150
ARTICLE_MAX_WORDS = 400
SYNTHESIS_MIN_WORDS = 400
SYNTHESIS_MAX_WORDS = 600

# Categories
CATEGORIES = [
    "markets",
    "macro",
    "crypto",
    "personal-finance",
    "real-estate",
    "tech",
    "commodities",
    "international",
    "deals",
]
