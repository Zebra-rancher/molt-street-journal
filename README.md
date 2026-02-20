# Molt Street Journal

Financial news for humans and agents. AI reporters synthesize articles from RSS feeds; the site serves HTML for humans and structured JSON + raw markdown for AI agents.

## Architecture

```
RSS Feeds → fetch_rss.py → raw JSON → generate_articles.py → markdown articles → build_site.py → static site
```

Three scripts, five Python packages, no frameworks, no JavaScript.

## Local Development

```bash
pip install -r requirements.txt
cd scripts && python build_site.py
cd ../output && python -m http.server 8000
```

## Next Steps

### 1. Add Anthropic API key to GitHub

```bash
gh secret set ANTHROPIC_API_KEY --repo Zebra-rancher/molt-street-journal
```

Paste your `sk-ant-...` key when prompted. Required for the article generation step.

### 2. Enable GitHub Pages

Repo Settings → Pages → Source: **GitHub Actions**

### 3. Configure DNS

Add a CNAME record for `moltstreetjournal.com` pointing to `zebra-rancher.github.io`.

### 4. Test the workflow

Actions tab → "Fetch, Generate & Publish" → **Run workflow**

Verify new articles appear on the site within a few minutes.

### 5. Polish (Phase 5)

- Article grouping (cluster related RSS items for synthesis)
- Category pages and archive page
- Failure notifications
- Tune reporter system prompt based on output quality
