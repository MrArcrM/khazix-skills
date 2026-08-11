#!/usr/bin/env python3
"""Render share-daily-tip JSON to a self-contained HTML page."""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_HERO = SKILL_DIR / "assets" / "hero.jpg"
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
HASHTAG_RE = re.compile(r"#[A-Za-z0-9_一-鿿]+")


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def hero_data_uri(path: Path = DEFAULT_HERO) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def linkify_summary(text: str) -> str:
    placeholders: dict[str, str] = {}

    def stash(snippet: str) -> str:
        key = f"\x00P{len(placeholders)}\x00"
        placeholders[key] = snippet
        return key

    def sub_url(m: re.Match) -> str:
        url = m.group(0)
        trail = ""
        while url and url[-1] in ".,;:!?)）】」』":
            trail = url[-1] + trail
            url = url[:-1]
        href = html.escape(url, quote=True)
        body = html.escape(url, quote=False)
        return stash(f'<a href="{href}" target="_blank" rel="noopener" class="inline-link">{body}</a>') + trail

    def sub_hashtag(m: re.Match) -> str:
        tag = html.escape(m.group(0), quote=False)
        return stash(f'<span class="hashtag">{tag}</span>')

    text = URL_RE.sub(sub_url, text or "")
    text = HASHTAG_RE.sub(sub_hashtag, text)
    text = html.escape(text, quote=False)
    for key, snippet in placeholders.items():
        text = text.replace(key, snippet)
    return text


def source_kind(source: str) -> str:
    if source.startswith("X："):
        return "X"
    if source.startswith("公众号："):
        return "公众号"
    if "RSS" in source or "Hacker News" in source:
        return "媒体/RSS"
    return "其他"


def render_item(item: dict, idx: int) -> str:
    title = esc(item.get("title"))
    url = esc(item.get("url"))
    source = esc(item.get("source") or "未知来源")
    kind = esc(source_kind(item.get("source") or ""))
    time_bj = esc(item.get("time_bj"))
    summary_html = linkify_summary(item.get("summary", ""))
    return f"""
<article class="item">
  <div class="num" aria-hidden="true">{idx}</div>
  <div class="body">
    <h2><a href="{url}" target="_blank" rel="noopener">{title}</a></h2>
    <p class="source"><span>{time_bj}</span><span>{source}</span><span class="kind">{kind}</span></p>
    <p class="summary">{summary_html}</p>
  </div>
</article>"""


def render(data: dict) -> str:
    date = data.get("date", "")
    items = data.get("items", [])
    min_score = data.get("min_score", 55)
    rows = "\n".join(render_item(item, idx) for idx, item in enumerate(items, 1))
    hero_uri = hero_data_uri()
    hero_html = f'<figure class="hero"><img src="{hero_uri}" alt=""></figure>' if hero_uri else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex, nofollow">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#fdfcf9">
<title>AI 每日技巧&观点 {esc(date)}</title>
<style>
:root {{
  --bg: #f0eee6;
  --ink: #141413;
  --soft: #3d3d3a;
  --muted: #87867f;
  --line: #e0ddd2;
  --line-soft: #e8e6dc;
  --accent: #c46849;
  --tag-bg: #e8e6dc;
  --tag-ink: #6b6862;
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  line-height: 1.75;
  -webkit-font-smoothing: antialiased;
  -webkit-text-size-adjust: 100%;
}}
.container {{ max-width: 720px; margin: 0 auto; padding: 48px 24px 80px; }}
figure.hero {{
  margin: 12px 0 0;
  border-radius: 8px;
  overflow: hidden;
  line-height: 0;
}}
figure.hero img {{
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 21 / 9;
  object-fit: cover;
}}
header.page {{
  margin-bottom: 0;
  padding-bottom: 0;
  text-align: center;
}}
header.page h1 {{
  font-size: 28px;
  font-weight: 700;
  margin: 0 0 8px;
  line-height: 1.2;
  letter-spacing: -0.01em;
}}
header.page .meta {{
  color: var(--muted);
  font-size: 14px;
}}
.toolbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 18px 0 56px;
  gap: 12px;
  padding: 0 8px;
}}
.toolbar .hint {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.4;
}}
.toolbar .hint svg {{
  width: 13px;
  height: 13px;
  flex-shrink: 0;
  opacity: 0.85;
}}
.share-btn {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  background: transparent;
  border: none;
  color: var(--muted);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s;
  flex: 0 0 auto;
  -webkit-appearance: none;
  appearance: none;
}}
.share-btn:hover, .share-btn.copied {{ color: var(--accent); }}
.share-btn svg {{
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}}
.item {{
  position: relative;
  padding: 0 0 30px;
  margin: 0 0 30px;
  border-bottom: 1px solid var(--line-soft);
}}
.item:last-of-type {{ border-bottom: 0; margin-bottom: 0; }}
.num {{
  position: absolute;
  top: -8px;
  right: 0;
  color: rgba(23, 23, 22, .045);
  font-size: 58px;
  font-weight: 850;
  line-height: 1;
  letter-spacing: 0;
  pointer-events: none;
  user-select: none;
}}
.body {{ min-width: 0; padding-right: 58px; }}
h2 {{ margin: 0 0 8px; font-size: 20px; line-height: 1.38; letter-spacing: 0; }}
h2 a {{ color: var(--ink); text-decoration: none; }}
h2 a:hover {{ color: var(--accent); text-decoration: underline; }}
.source {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 12px; color: var(--muted); font-size: 13px; line-height: 1.45; }}
.kind {{ background: var(--tag-bg); color: var(--tag-ink); border-radius: 4px; padding: 1px 7px; }}
.summary {{ margin: 0; color: var(--soft); font-size: 16px; }}
.inline-link {{ color: var(--soft); text-decoration: underline dotted; text-underline-offset: 3px; word-break: break-all; }}
.inline-link:hover {{ color: var(--accent); text-decoration-style: solid; }}
.hashtag {{ color: var(--muted); font-size: .88em; opacity: .65; }}
footer.page {{ margin-top: 64px; padding-top: 24px; border-top: 1px solid var(--line); text-align: center; color: var(--muted); font-size: 13px; line-height: 1.6; }}
@media (max-width: 640px) {{
  .container {{ padding: 28px 16px 64px; }}
  figure.hero {{ margin: 16px 0 0; border-radius: 6px; }}
  header.page {{ margin-bottom: 32px; padding-bottom: 20px; }}
  header.page h1 {{ font-size: 24px; }}
  .toolbar {{ margin: 14px 0 40px; padding: 0 6px; }}
  .toolbar .hint {{ font-size: 12px; }}
  .share-btn {{ font-size: 13px; }}
  .share-btn svg {{ width: 14px; height: 14px; }}
  .body {{ padding-right: 42px; }}
  .num {{ font-size: 42px; top: -4px; }}
  h2 {{ font-size: 18px; }}
  .summary {{ font-size: 15.5px; }}
}}
</style>
</head>
<body>
<div class="container">
  <header class="page">
    <h1>AI 每日技巧&观点 · {esc(date)}</h1>
    <div class="meta">共 {len(items)} 条</div>
  </header>
  {hero_html}

  <div class="toolbar">
    <p class="hint">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10"/>
        <line x1="12" y1="16" x2="12" y2="12"/>
        <line x1="12" y1="8" x2="12.01" y2="8"/>
      </svg>
      <span>标题可跳转</span>
    </p>
    <button type="button" class="share-btn" onclick="shareCopy(this)" aria-label="复制本页链接">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>
      </svg>
      <span class="share-label">分享</span>
    </button>
  </div>

  <main>
    {rows}
  </main>

  <footer class="page">
    全量 tip · 去掉精选 · 分数 {min_score}+ · 按分数降序
  </footer>
</div>
<script>
function shareCopy(btn) {{
  var url = window.location.href;
  var label = btn.querySelector('.share-label');
  if (!label.dataset.orig) label.dataset.orig = label.textContent;
  function done() {{
    label.textContent = '已复制';
    btn.classList.add('copied');
    setTimeout(function () {{
      label.textContent = label.dataset.orig;
      btn.classList.remove('copied');
    }}, 1800);
  }}
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(url).then(done, function () {{ legacyCopy(url); done(); }});
  }} else {{
    legacyCopy(url); done();
  }}
}}
function legacyCopy(text) {{
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {{ document.execCommand('copy'); }} catch (e) {{}}
  document.body.removeChild(ta);
}}
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="render AI HOT daily tip HTML")
    ap.add_argument("input", help="input JSON path")
    ap.add_argument("output", help="output HTML path")
    args = ap.parse_args()

    inp = Path(args.input)
    out = Path(args.output)
    data = json.loads(inp.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(data), encoding="utf-8")
    print(f"wrote {out} — {len(data.get('items', []))} items", flush=True)


if __name__ == "__main__":
    main()
