#!/usr/bin/env python3
"""按 $DATE hash 从 hero_prompts.json 抽 prompt → gpt-image 生成 21:9 → sips 压成 jpg → 覆盖 assets/hero.jpg

用法:
    python3 gen_hero.py YYYY-MM-DD

退出码:
    0 = 成功（hero.jpg 已更新）
    1 = 失败（生成/网络/压缩任一步出错，hero.jpg 未动）
    2 = 参数错误

注意:
    - 失败时**不**修改 assets/hero.jpg，调用方应继续用现有图（不要阻断流程）
    - 同一 $DATE 反复跑命中同一基调（hash 确定性）
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
PROMPTS_JSON = SKILL_DIR / "scripts" / "hero_prompts.json"
HERO_JPG = SKILL_DIR / "assets" / "hero.jpg"
STATE_JSON = SKILL_DIR / "assets" / "hero-state.json"
WORK_DIR = Path("/tmp/aihot-daily")


def pick(date: str, candidates: list, avoid_palette: str | None = None) -> tuple[dict, int, int]:
    """按 $DATE md5 hash 选一条基调；若 avoid_palette 给定，向后滑动跳过同 palette 的相邻条。

    返回 (chosen, base_idx, final_idx)，便于调用方 log 出 hash 命中 vs 实际选中的差异。
    """
    h = int(hashlib.md5(date.encode()).hexdigest(), 16)
    n = len(candidates)
    base_idx = h % n
    if avoid_palette is None:
        return candidates[base_idx], base_idx, base_idx
    for offset in range(n):
        idx = (base_idx + offset) % n
        if candidates[idx]["palette"] != avoid_palette:
            return candidates[idx], base_idx, idx
    return candidates[base_idx], base_idx, base_idx


def load_state() -> dict | None:
    if not STATE_JSON.exists():
        return None
    try:
        return json.loads(STATE_JSON.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def save_state(date: str, chosen: dict) -> None:
    STATE_JSON.parent.mkdir(parents=True, exist_ok=True)
    STATE_JSON.write_text(json.dumps({
        "last_date": date,
        "last_id": chosen["id"],
        "last_palette": chosen["palette"],
        "last_subject": chosen["subject"],
    }, ensure_ascii=False, indent=2) + "\n")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: gen_hero.py YYYY-MM-DD", file=sys.stderr)
        return 2
    date = sys.argv[1]
    WORK_DIR.mkdir(parents=True, exist_ok=True)

    data = json.loads(PROMPTS_JSON.read_text())
    state = load_state()
    avoid = state["last_palette"] if state and state.get("last_date") != date else None
    chosen, base_idx, final_idx = pick(date, data["candidates"], avoid)
    full_prompt = f"{data['common_head']} {chosen['body']}, {data['common_tail']}"
    out_name = f"hero-{date}-{chosen['id']}"

    if final_idx != base_idx:
        print(f"📅 {date} → hash idx={base_idx} 撞昨日 palette '{avoid}'，滑到 idx={final_idx}",
              file=sys.stderr)
    print(f"📅 {date} → 🎨 {chosen['palette']} / {chosen['subject']} ({chosen['id']})",
          file=sys.stderr)

    # Step 1: gpt-image 生成
    try:
        subprocess.run(
            ["gpt-image", full_prompt,
             "--size", data["size"], "--quality", "high",
             "--op", str(WORK_DIR), "--name", out_name],
            check=True, capture_output=True, text=True, timeout=180,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"❌ gpt-image 失败: {e}", file=sys.stderr)
        return 1

    # gpt-image 输出文件名: '时间戳-{name}.png'，glob 找最近的
    candidates_png = sorted(
        WORK_DIR.glob(f"*{out_name}.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates_png:
        print(f"❌ 没找到生成的 png（pattern: *{out_name}.png）", file=sys.stderr)
        return 1
    src_png = candidates_png[0]
    if src_png.stat().st_size == 0:
        print(f"❌ 生成的 png 是 0 字节: {src_png}", file=sys.stderr)
        src_png.unlink(missing_ok=True)
        return 1

    # Step 2: sips 缩到 1280 + jpg quality 88
    tmp_resized = WORK_DIR / f".tmp-{out_name}.png"
    tmp_jpg = WORK_DIR / f"{out_name}.jpg"
    try:
        subprocess.run(
            ["sips", "-Z", "1280", str(src_png), "--out", str(tmp_resized)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["sips", "-s", "format", "jpeg", "-s", "formatOptions", "88",
             str(tmp_resized), "--out", str(tmp_jpg)],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ sips 压缩失败: {e}", file=sys.stderr)
        return 1
    finally:
        tmp_resized.unlink(missing_ok=True)

    # Step 3: 覆盖 assets/hero.jpg
    HERO_JPG.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_jpg, HERO_JPG)
    size_kb = HERO_JPG.stat().st_size // 1024
    save_state(date, chosen)
    print(f"✅ hero.jpg 已更新 ({size_kb}KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
