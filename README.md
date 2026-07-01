# AU & NZ Agriculture News Digest

Daily-refreshed dashboard of Australian and New Zealand agriculture news, built from
curated RSS feeds and summarized with Claude.

**Live dashboard:** enabled via GitHub Pages, served from `docs/index.html`.

## How it works

1. `scripts/fetch_and_build.py` pulls each feed listed in `scripts/feeds.json`.
2. Articles published in the last 36 hours are kept, deduplicated by URL.
3. All articles are sent to Claude (`claude-opus-4-8`) in a single batched
   request, which returns a concise 1-2 sentence summary per article as
   structured JSON. If the API call fails (no key, rate limit, network),
   falls back to a local extractive summary so the pipeline never breaks.
4. A static `docs/index.html` dashboard is regenerated, plus a dated JSON
   archive under `docs/data/`.

## Running manually

```
pip install -r scripts/requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
python scripts/fetch_and_build.py
```

Then open `docs/index.html` in a browser, or commit + push to update the
live GitHub Pages site.

## Sources

See `scripts/feeds.json`. Currently: Beef Central, The Land, Farm Weekly,
Stock & Land (AU) and Farmers Weekly NZ, RNZ Country, Rural News Group (NZ).
Add more by appending `{ "name": ..., "country": "AU"|"NZ", "url": ... }`.

## Automation

A GitHub Actions workflow (`.github/workflows/daily-digest.yml`) runs daily
(20:06 UTC / 06:06 AEST), rebuilds the dashboard, and pushes the update —
entirely on GitHub's infrastructure, independent of any local machine.
Requires the `ANTHROPIC_API_KEY` repository secret to be set for AI
summaries (Settings → Secrets and variables → Actions).
