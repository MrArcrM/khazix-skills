#!/usr/bin/env python3
"""aihot daily HTML 渲染器：吃 remix 后的 JSON + 选主题 → 出 self-contained HTML。

输入 JSON 结构（agent 在 share-daily 流程 Step 3 写出）：
{
  "date": "YYYY-MM-DD",
  "sections": [
    {
      "label": "模型",
      "items": [
        {
          "title": "...",
          "source": "...",
          "source_role": "官方·X",
          "summary": "...",
          "url": "https://..."
        }
      ]
    }
  ]
}

视觉层在 themes/<name>/ 下：template.html.j2 + style.css + meta.json。
本脚本只负责数据准备 + 选主题 + 喂 Jinja2 渲染，不写任何 CSS/HTML。

用法：
  python3 render_daily_html.py <input.json> <output.html>
  python3 render_daily_html.py <input.json> <output.html> --theme <name>
  python3 render_daily_html.py --list-themes
"""

import sys
import re
import json
import html
import base64
import argparse
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

SKILL_DIR = Path(__file__).resolve().parent.parent
THEMES_DIR = SKILL_DIR / "themes"
DEFAULT_HERO = SKILL_DIR / "assets" / "hero.jpg"
DEFAULT_THEME = "claude-light"


def hero_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    suffix = path.suffix.lower().lstrip(".")
    mime = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "webp": "image/webp", "svg": "image/svg+xml",
    }.get(suffix, "application/octet-stream")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


# 只匹配 RFC 3986 允许的 ASCII URL 字符；任何 CJK 字符自然终止 URL，避免
# 「http://example.com/path后面跟中文」被整段吞掉（带链接 404 的根因）。
URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
HASHTAG_RE = re.compile(r"#[A-Za-z0-9_一-鿿]+")


def parse_source(name: str) -> tuple[str, str]:
    """从 API sourceName 解析出 (badge, body)。无 source_role 时的兜底。"""
    if name.startswith("X："):
        return "X", name[2:]
    for tail, badge in (("（RSS）", "RSS"), ("（网页）", "网页")):
        if name.endswith(tail):
            return badge, name[: -len(tail)]
    return "", name


def linkify_summary(text: str) -> str:
    """summary 内 URL → 可点 link，hashtag → 弱化 span，其余 escape。返回 HTML 片段。"""
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
        if not url:
            return m.group(0)
        href = html.escape(url, quote=True)
        body = html.escape(url, quote=False)
        return stash(f'<a href="{href}" target="_blank" rel="noopener" class="inline-link">{body}</a>') + trail

    def sub_hashtag(m: re.Match) -> str:
        tag = m.group(0)
        return stash(f'<span class="hashtag">{html.escape(tag, quote=False)}</span>')

    text = URL_RE.sub(sub_url, text)
    text = HASHTAG_RE.sub(sub_hashtag, text)
    text = html.escape(text, quote=False)
    for key, snippet in placeholders.items():
        text = text.replace(key, snippet)
    return text


def list_themes() -> list[dict]:
    """扫 themes/ 目录返回所有主题元信息列表（按名字排序，default 在前）。"""
    if not THEMES_DIR.is_dir():
        return []
    themes = []
    for d in sorted(THEMES_DIR.iterdir()):
        meta_path = d / "meta.json"
        if not (d.is_dir() and meta_path.exists()):
            continue
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["_dir"] = d
        themes.append(meta)
    themes.sort(key=lambda m: (not m.get("default", False), m.get("name", "")))
    return themes


def load_theme(name: str) -> tuple[Path, dict, str]:
    theme_dir = THEMES_DIR / name
    if not theme_dir.is_dir():
        avail = ", ".join(t.get("name", "?") for t in list_themes()) or "(none)"
        raise SystemExit(f"theme not found: {name}. available: {avail}")
    meta_path = theme_dir / "meta.json"
    css_path = theme_dir / "style.css"
    tmpl_path = theme_dir / "template.html.j2"
    for p in (meta_path, css_path, tmpl_path):
        if not p.exists():
            raise SystemExit(f"theme {name} missing required file: {p.name}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    css = css_path.read_text(encoding="utf-8")
    return theme_dir, meta, css


def build_context(data: dict, hero_path=None) -> dict:
    """JSON → Jinja2 模板 context。所有视觉无关的预处理都在这里。"""
    sections_ctx = []
    section_counts = []
    idx = 1
    for section in data.get("sections", []):
        items_ctx = []
        for item in section.get("items", []):
            role = item.get("source_role", "")
            src_text = item.get("source", "")
            if role:
                badge, body = role, src_text
            else:
                badge, body = parse_source(src_text)
            items_ctx.append({
                "idx": idx,
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "badge": badge,
                "src_body": body,
                "summary_html": linkify_summary(item.get("summary", "")),
            })
            idx += 1
        label = section.get("label", "")
        # 字段叫 entries 不叫 items：Jinja2 里 dict.items 是 method 会劫持属性访问
        sections_ctx.append({"label": label, "entries": items_ctx})
        section_counts.append((label, len(section.get("items", []))))
    total = idx - 1
    section_stats = " · ".join(f"{l} {n}" for l, n in section_counts if n > 0)
    date = data.get("date", "")
    return {
        "title": f"AI HOT 日报 · {date}",
        "date": date,
        "total": total,
        "section_stats": section_stats,
        "hero_uri": hero_data_uri(hero_path or DEFAULT_HERO),
        "sections": sections_ctx,
    }


def render(data: dict, theme: str = DEFAULT_THEME, hero_path=None) -> str:
    theme_dir, _meta, css = load_theme(theme)
    env = Environment(
        loader=FileSystemLoader(str(theme_dir)),
        autoescape=select_autoescape(enabled_extensions=("html", "j2", "html.j2")),
        trim_blocks=False,
        lstrip_blocks=False,
    )
    tmpl = env.get_template("template.html.j2")
    ctx = build_context(data, hero_path=hero_path)
    ctx["css"] = css
    return tmpl.render(**ctx)


def main() -> None:
    ap = argparse.ArgumentParser(description="aihot daily HTML 渲染器")
    ap.add_argument("input", nargs="?", help="输入 JSON 路径")
    ap.add_argument("output", nargs="?", help="输出 HTML 路径")
    ap.add_argument("--theme", default=DEFAULT_THEME, help=f"主题名（默认 {DEFAULT_THEME}）")
    ap.add_argument("--list-themes", action="store_true", help="列出所有可用主题后退出")
    args = ap.parse_args()

    if args.list_themes:
        themes = list_themes()
        if not themes:
            print("(no themes found in themes/)", file=sys.stderr)
            sys.exit(1)
        for m in themes:
            tag = " [default]" if m.get("default") else ""
            print(f"{m.get('name','?'):20s} {m.get('label','')}{tag}")
            desc = m.get("description", "")
            if desc:
                print(f"{'':20s}   {desc}")
        return

    if not args.input or not args.output:
        ap.error("input 和 output 必填（除非用 --list-themes）")

    inp = Path(args.input)
    out = Path(args.output)
    data = json.loads(inp.read_text(encoding="utf-8"))
    html_text = render(data, theme=args.theme)
    out.write_text(html_text, encoding="utf-8")
    print(f"wrote {out} (theme={args.theme})", file=sys.stderr)


if __name__ == "__main__":
    main()
