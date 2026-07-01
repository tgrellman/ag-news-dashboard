#!/usr/bin/env python3
"""Fetch AU/NZ agriculture RSS feeds, summarize with Claude, and build a
static dashboard (docs/index.html) for GitHub Pages.
"""
import html
import json
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDS_PATH = os.path.join(SCRIPT_DIR, "feeds.json")
DOCS_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "docs"))
DATA_DIR = os.path.join(DOCS_DIR, "data")

LOOKBACK_HOURS = 36
USER_AGENT = "Mozilla/5.0 (compatible; AgNewsDigestBot/1.0)"
CLAUDE_MODEL = "claude-opus-4-8"
MAX_DESC_CHARS = 600


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def clean_text(raw):
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def summarize(text, max_sentences=2, max_chars=280):
    if not text:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    summary = " ".join(sentences[:max_sentences]).strip()
    if len(summary) > max_chars:
        summary = summary[:max_chars].rsplit(" ", 1)[0] + "…"
    return summary


def parse_date(value):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def parse_feed(xml_bytes, source_name, country):
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for it in root.findall(".//item"):
        title = clean_text(it.findtext("title") or "")
        link = (it.findtext("link") or "").strip()
        desc = it.findtext("description") or ""
        pub_raw = it.findtext("pubDate")
        pub_dt = parse_date(pub_raw)
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "description_clean": clean_text(desc)[:MAX_DESC_CHARS],
                "summary": "",
                "published": pub_dt.isoformat() if pub_dt else None,
                "source": source_name,
                "country": country,
            }
        )
    return items


def load_feeds():
    with open(FEEDS_PATH, encoding="utf-8") as f:
        return json.load(f)


def collect_articles():
    articles = []
    seen_links = set()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)
    for feed in load_feeds():
        try:
            raw = fetch(feed["url"])
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"[warn] failed to fetch {feed['name']}: {e}")
            continue
        for item in parse_feed(raw, feed["name"], feed["country"]):
            link_key = item["link"].split("?")[0].rstrip("/")
            if link_key in seen_links:
                continue
            if item["published"]:
                pub_dt = datetime.fromisoformat(item["published"])
                if pub_dt < cutoff:
                    continue
            seen_links.add(link_key)
            articles.append(item)
    articles.sort(key=lambda a: a["published"] or "", reverse=True)
    return articles


def summarize_with_claude(articles):
    """Batch-summarize all articles in a single Claude API call. Returns a
    dict of {article_index: summary}. Raises on any failure so the caller
    can fall back to extractive summaries."""
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    numbered = [
        f"{i}. TITLE: {a['title']}\nDESCRIPTION: {a['description_clean'] or '(no description available)'}"
        for i, a in enumerate(articles)
    ]
    prompt = (
        "Below are agriculture news articles from Australia and New Zealand, each with a "
        "numbered index, title, and description. Write a concise, neutral 1-2 sentence "
        "summary for each article capturing the key facts. Do not add commentary, "
        "opinions, or details not present in the source text.\n\n" + "\n\n".join(numbered)
    )
    schema = {
        "type": "object",
        "properties": {
            "summaries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "summary": {"type": "string"},
                    },
                    "required": ["index", "summary"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["summaries"],
        "additionalProperties": False,
    }
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return {item["index"]: item["summary"].strip() for item in data["summaries"]}


def apply_summaries(articles):
    """Fill in each article's `summary` field, preferring Claude-generated
    summaries and falling back to a local extractive summary on failure."""
    by_index = {}
    if articles:
        try:
            by_index = summarize_with_claude(articles)
        except Exception as e:
            print(f"[warn] Claude summarization failed, using extractive fallback: {e}")
    for i, a in enumerate(articles):
        a["summary"] = by_index.get(i) or summarize(a["description_clean"])


def time_ago(iso_str, now):
    if not iso_str:
        return "undated"
    dt = datetime.fromisoformat(iso_str)
    delta = now - dt
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        mins = max(1, int(delta.total_seconds() // 60))
        return f"{mins} min ago"
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AU &amp; NZ Agriculture News Digest</title>
<style>
  :root {{
    --bg: #f4f6f2; --card: #ffffff; --ink: #1f2a1a; --muted: #5c6b56;
    --accent: #3f7d3f; --accent-dark: #2d5a2d; --border: #e0e5db;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    background: var(--bg); color: var(--ink);
  }}
  header {{
    background: linear-gradient(135deg, var(--accent-dark), var(--accent));
    color: #fff; padding: 28px 20px;
  }}
  header h1 {{ margin: 0 0 4px; font-size: 1.6rem; }}
  header p {{ margin: 0; opacity: 0.9; font-size: 0.9rem; }}
  .wrap {{ max-width: 960px; margin: 0 auto; padding: 20px; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }}
  .filters button {{
    border: 1px solid var(--border); background: var(--card); color: var(--ink);
    padding: 6px 14px; border-radius: 999px; cursor: pointer; font-size: 0.85rem;
  }}
  .filters button.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }}
  .card {{
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 8px;
  }}
  .card .meta {{ display: flex; justify-content: space-between; font-size: 0.75rem; color: var(--muted); }}
  .card .badge {{
    background: #eaf2e6; color: var(--accent-dark); padding: 2px 8px; border-radius: 999px; font-weight: 600;
  }}
  .card a.title {{ font-size: 1.02rem; font-weight: 600; color: var(--ink); text-decoration: none; line-height: 1.35; }}
  .card a.title:hover {{ color: var(--accent-dark); text-decoration: underline; }}
  .card p.summary {{ margin: 0; font-size: 0.88rem; color: var(--muted); line-height: 1.4; }}
  .empty {{ text-align: center; color: var(--muted); padding: 60px 20px; }}
  footer {{ text-align: center; color: var(--muted); font-size: 0.8rem; padding: 30px 20px 50px; }}
</style>
</head>
<body>
<header>
  <h1>Australia &amp; New Zealand Agriculture News Digest</h1>
  <p>{article_count} articles from the last {lookback_hours}h &middot; generated {generated_display} UTC</p>
</header>
<div class="wrap">
  <div class="filters" id="filters">
    <button data-filter="all" class="active">All</button>
    <button data-filter="AU">Australia</button>
    <button data-filter="NZ">New Zealand</button>
  </div>
  <div class="grid" id="grid">
{cards}
  </div>
  {empty_block}
</div>
<footer>Sources: {source_list}. Summaries generated by Claude.</footer>
<script>
  const buttons = document.querySelectorAll('#filters button');
  const cards = document.querySelectorAll('#grid .card');
  buttons.forEach(btn => {{
    btn.addEventListener('click', () => {{
      buttons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const filter = btn.dataset.filter;
      cards.forEach(c => {{
        c.style.display = (filter === 'all' || c.dataset.country === filter) ? '' : 'none';
      }});
    }});
  }});
</script>
</body>
</html>
"""

CARD_TEMPLATE = """    <div class="card" data-country="{country}">
      <div class="meta"><span class="badge">{country}</span><span>{source} &middot; {age}</span></div>
      <a class="title" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
      <p class="summary">{summary}</p>
    </div>"""


def render_html(articles, generated_at):
    now = generated_at
    cards = []
    sources = sorted({a["source"] for a in articles})
    for a in articles:
        cards.append(
            CARD_TEMPLATE.format(
                country=html.escape(a["country"]),
                source=html.escape(a["source"]),
                age=html.escape(time_ago(a["published"], now)),
                link=html.escape(a["link"], quote=True),
                title=html.escape(a["title"]),
                summary=html.escape(a["summary"]) if a["summary"] else "<em>No summary available.</em>",
            )
        )
    empty_block = "" if articles else '<div class="empty">No articles found in the lookback window.</div>'
    return PAGE_TEMPLATE.format(
        article_count=len(articles),
        lookback_hours=LOOKBACK_HOURS,
        generated_display=now.strftime("%Y-%m-%d %H:%M"),
        cards="\n".join(cards),
        empty_block=empty_block,
        source_list=", ".join(sources) if sources else "none reachable",
    )


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    articles = collect_articles()
    apply_summaries(articles)
    generated_at = datetime.now(timezone.utc)

    index_path = os.path.join(DOCS_DIR, "index.html")
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(render_html(articles, generated_at))

    archive_path = os.path.join(DATA_DIR, generated_at.strftime("%Y-%m-%d") + ".json")
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=2)

    print(f"Wrote {len(articles)} articles to {index_path}")


if __name__ == "__main__":
    main()
