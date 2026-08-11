#!/usr/bin/env python3
"""Fetch one Beijing day's full aihot tip items for share-daily-tip.

Output JSON shape:
{
  "date": "YYYY-MM-DD",
  "category": "tip",
  "min_score": 55,
  "exclude_selected": true,
  "items": [
    {
      "title": "...",
      "source": "...",
      "publishedAt": "...",
      "time_bj": "HH:MM",
      "score": 72,
      "selected": false,
      "summary": "...",
      "url": "..."
    }
  ],
  "stats": {...}
}

Usage:
  python3 fetch_daily_tip_items.py <YYYY-MM-DD> <output.json> [--min-score 55]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BASE = "https://aihot.virxact.com/api/public/items"
BJ = timezone(timedelta(hours=8))


def fetch_json(params: dict[str, str]) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def bj_day_start(date: str) -> datetime:
    return datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=BJ)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_item_time(item: dict) -> datetime | None:
    ts = item.get("publishedAt")
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(BJ)


def slim_item(item: dict, dt_bj: datetime) -> dict:
    return {
        "id": item.get("id", ""),
        "title": item.get("title", ""),
        "title_en": item.get("title_en"),
        "source": item.get("source", ""),
        "publishedAt": item.get("publishedAt"),
        "time_bj": dt_bj.strftime("%H:%M"),
        "score": int(item.get("score") or 0),
        "selected": bool(item.get("selected")),
        "summary": item.get("summary", ""),
        "url": item.get("url", ""),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="fetch full daily tip items from AI HOT")
    ap.add_argument("date", help="Beijing date, YYYY-MM-DD")
    ap.add_argument("output", help="output JSON path")
    ap.add_argument("--min-score", type=int, default=55, help="minimum score, inclusive")
    ap.add_argument("--include-selected", action="store_true", help="keep AI HOT selected items")
    args = ap.parse_args()

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        print(f"invalid date format: {args.date} (want YYYY-MM-DD)", file=sys.stderr)
        sys.exit(2)

    start_bj = bj_day_start(args.date)
    end_bj = start_bj + timedelta(days=1)
    since = iso_utc(start_bj)

    raw_items: list[dict] = []
    cursor = None
    pages = 0
    while True:
        params = {
            "mode": "all",
            "category": "tip",
            "since": since,
            "take": "100",
        }
        if cursor:
            params["cursor"] = cursor
        try:
            data = fetch_json(params)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"fetch failed: HTTP {e.code} {body}", file=sys.stderr)
            sys.exit(1)
        pages += 1
        raw_items.extend(data.get("items", []))
        cursor = data.get("nextCursor")
        if not data.get("hasNext") or not cursor:
            break
        time.sleep(0.25)

    seen: set[str] = set()
    same_day: list[dict] = []
    selected_removed = 0
    low_score_removed = 0
    for item in raw_items:
        dt_bj = parse_item_time(item)
        if not dt_bj or not (start_bj <= dt_bj < end_bj):
            continue
        key = item.get("id") or item.get("url")
        if key in seen:
            continue
        seen.add(key)
        score = int(item.get("score") or 0)
        selected = bool(item.get("selected"))
        if selected and not args.include_selected:
            selected_removed += 1
            continue
        if score < args.min_score:
            low_score_removed += 1
            continue
        same_day.append(slim_item(item, dt_bj))

    same_day.sort(key=lambda it: (it["score"], it.get("publishedAt") or ""), reverse=True)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": args.date,
        "category": "tip",
        "min_score": args.min_score,
        "exclude_selected": not args.include_selected,
        "items": same_day,
        "stats": {
            "pages": pages,
            "raw_fetched": len(raw_items),
            "kept": len(same_day),
            "selected_removed": selected_removed,
            "low_score_removed": low_score_removed,
            "window_bj": {
                "start": start_bj.isoformat(),
                "end": end_bj.isoformat(),
            },
        },
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        "wrote "
        f"{out} — kept {len(same_day)} items "
        f"(removed {selected_removed} selected, {low_score_removed} below score {args.min_score})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
