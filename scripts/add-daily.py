#!/usr/bin/env python3
"""
add-daily.py — 從 worldcup-daily/<DATE>/ cp 一篇 daily 到 articles/，加好 frontmatter、跑 build

用法：
    python3 scripts/add-daily.py 2026-06-04          # 從 worldcup-daily/2026-06-04/medium-publish.md
    python3 scripts/add-daily.py 2026-06-04 --vol 4  # 強指定 vol（一般會從檔案內 Vol. NNN 自動抓）

副作用：
- 建 articles/daily-<DATE>/index.md + cover/table 圖
- 跑 build-articles.py 生 public/articles/
- print git status，由你決定 commit + push
"""

import datetime
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC_BASE = pathlib.Path.home() / "Library/CloudStorage/Dropbox/AI/CoWork/worldcup-daily"


def parse_args(argv):
    args = argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    date_str = args[0]
    try:
        datetime.date.fromisoformat(date_str)
    except ValueError:
        print(f"❌ '{date_str}' 不是 YYYY-MM-DD 格式")
        sys.exit(1)
    vol_override = None
    if "--vol" in args:
        i = args.index("--vol")
        vol_override = int(args[i + 1])
    return date_str, vol_override


def read_source(date_str: str) -> tuple[str, pathlib.Path]:
    src_dir = SRC_BASE / date_str
    md_path = src_dir / "medium-publish.md"
    if not md_path.exists():
        print(f"❌ source 不存在：{md_path}")
        sys.exit(2)
    return md_path.read_text(encoding="utf-8"), src_dir


def extract_title(text: str) -> str:
    m = re.search(r"^# (.+?)$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def extract_vol(text: str) -> int | None:
    m = re.search(r"每日戰報\s*Vol\.\s*(\d+)", text)
    return int(m.group(1)) if m else None


def extract_lede(src_dir: pathlib.Path) -> str:
    """從 draft-v2.md frontmatter 撈 lede（站上 AEO 重點速答盒 + meta description）。
    medium-publish.md 不帶 frontmatter，lede 的 source of truth 是 draft-v2.md（SOP §13.1）。"""
    draft = src_dir / "draft-v2.md"
    if not draft.exists():
        return ""
    text = draft.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 4)
    if end < 0:
        return ""
    fm = text[4:end]
    m = re.search(r"(?m)^lede:[ \t]*(.+?)[ \t]*$", fm)
    if not m:
        return ""
    val = m.group(1).strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        val = val[1:-1]
    return val.replace('\\"', '"').strip()


def build_frontmatter(slug: str, date_str: str, title: str, vol: int, lede: str = "") -> str:
    title_esc = title.replace('"', '\\"')
    lede_line = ""
    if lede:
        lede_esc = lede.replace('"', '\\"')
        lede_line = f'\nlede: "{lede_esc}"'
    return f"""---
slug: {slug}
type: "daily"
date: "{date_str}"
title: "{title_esc}"
subtitle: "2026 世界盃每日戰報 Vol. {vol:03d}"
vol: {vol}{lede_line}
---

"""


def cp_assets(src_dir: pathlib.Path, tgt_dir: pathlib.Path):
    tgt_dir.mkdir(parents=True, exist_ok=True)
    cover = src_dir / "cover.png"
    if cover.exists():
        shutil.copy2(cover, tgt_dir / "cover.png")
        print(f"   cover.png")
    for i in (1, 2):
        matches = sorted(src_dir.glob(f"table-{i}-*.png"))
        if matches:
            shutil.copy2(matches[0], tgt_dir / f"table-{i}.png")
            print(f"   table-{i}.png")


def main():
    date_str, vol_override = parse_args(sys.argv)
    slug = f"daily-{date_str}"
    tgt_dir = ROOT / "articles" / slug

    if tgt_dir.exists():
        print(f"⚠️  {tgt_dir.relative_to(ROOT)} 已存在 — 會覆寫 index.md + assets")

    print(f"📄 read source: {SRC_BASE}/{date_str}/medium-publish.md")
    text, src_dir = read_source(date_str)

    title = extract_title(text)
    if not title:
        print("❌ 沒抓到 H1 title")
        sys.exit(3)
    vol = vol_override or extract_vol(text)
    if vol is None:
        print("❌ 沒抓到 Vol. NNN，請用 --vol N")
        sys.exit(4)

    print(f"   title: {title}")
    print(f"   vol: {vol}")

    # AEO（SOP §13）：lede 從 draft-v2 frontmatter 帶上站；FAQ 走 medium-publish.md body
    lede = extract_lede(src_dir)
    if lede:
        print(f"   lede: {lede[:38]}…")
    else:
        print("   ⚠️  draft-v2.md 沒 lede — 站上不會有重點速答盒（補 SOP §13.1）")

    # strip 原 frontmatter（若有）
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 4)
        if end > 0:
            body = body[end + 4:].lstrip("\n")

    if not re.search(r"(?m)^##[ \t]+(常見問題|常見問答|FAQ)[ \t]*$", body):
        print("   ⚠️  body 沒有 ## 常見問題 — 站上不會有 FAQPage（SOP §13.2 daily 必附）")

    print(f"📁 cp assets → articles/{slug}/")
    cp_assets(src_dir, tgt_dir)

    (tgt_dir / "index.md").write_text(
        build_frontmatter(slug, date_str, title, vol, lede) + body, encoding="utf-8"
    )
    print(f"✅ articles/{slug}/index.md")

    print()
    print("🔨 build-articles.py …")
    res = subprocess.run(
        ["python3", str(ROOT / "scripts/build-articles.py")],
        cwd=ROOT, capture_output=True, text=True
    )
    print(res.stdout)
    if res.returncode != 0:
        print(res.stderr, file=sys.stderr)
        sys.exit(res.returncode)

    print()
    print("📋 git status:")
    subprocess.run(["git", "status", "--short"], cwd=ROOT)
    print()
    print(f"→ 確認 OK 後 commit:")
    print(f"   git add articles/{slug} public/articles/")
    print(f'   git commit -m "feat(articles): daily {date_str} Vol. {vol:03d}"')
    print(f"   git push origin main")


if __name__ == "__main__":
    main()
