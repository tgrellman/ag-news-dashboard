# AU & NZ Agriculture News Digest

Daily-refreshed dashboard of Australian and New Zealand agriculture news, built from
curated RSS feeds. No external services or API keys required.

**Live dashboard:** enabled via GitHub Pages, served from `docs/index.html`.

## How it works

1. `scripts/fetch_and_build.py` pulls each feed listed in `scripts/feeds.json`.
2. Articles published in the last 36 hours are kept, deduplicated by URL.
3. Each article gets a short extractive summary (first 1-2 sentences of its
   RSS description, cleaned of HTML) — no AI/LLM call involved.
4. A static `docs/index.html` dashboard is regenerated, plus a dated JSON
   archive under `docs/data/`.

## Running manually

```
python scripts/fetch_and_build.py
```

Then open `docs/index.html` in a browser, or commit + push to update the
live GitHub Pages site.

## Sources

See `scripts/feeds.json`. Currently: Beef Central, The Land, Farm Weekly,
Stock & Land (AU) and Farmers Weekly NZ, RNZ Country, Rural News Group (NZ).
Add more by appending `{ "name": ..., "country": "AU"|"NZ", "url": ... }`.

## Automation

A daily scheduled Claude Code cloud task runs the script and pushes the
updated dashboard to this repo automatically.
