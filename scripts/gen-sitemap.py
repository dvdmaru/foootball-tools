#!/usr/bin/env python3
"""gen-sitemap.py — 掃 public/ 內所有 index.html → public/sitemap.xml

自動涵蓋 /、/articles/（含每篇）、/standings/、/teams/（含 48 隊）。
新增任何 <dir>/index.html 都會自動進 sitemap，不必手動維護清單。
lastmod 取該 index.html 的 mtime（台北時間日期）。

跑序：所有 build script（gen-ics / build-articles / build-standings /
gen-team-pages）之後再跑，sitemap 才包含最新頁面。

用法：python3 scripts/gen-sitemap.py
"""

import pathlib
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
SITE = "https://foootball.twtools.cc"


def url_for(index_path: pathlib.Path) -> str:
    rel = index_path.parent.relative_to(PUBLIC)
    if str(rel) == ".":
        return f"{SITE}/"
    return f"{SITE}/{rel.as_posix()}/"


def lastmod(index_path: pathlib.Path) -> str:
    tp = datetime.utcfromtimestamp(index_path.stat().st_mtime) + timedelta(hours=8)
    return tp.strftime("%Y-%m-%d")


def build():
    entries = []
    for idx in sorted(PUBLIC.rglob("index.html")):
        entries.append((url_for(idx), lastmod(idx)))

    # 穩定排序：root 先，其餘字典序
    entries.sort(key=lambda e: (e[0] != f"{SITE}/", e[0]))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, mod in entries:
        lines.append(f"  <url><loc>{escape(loc)}</loc><lastmod>{mod}</lastmod></url>")
    lines.append("</urlset>")
    lines.append("")

    (PUBLIC / "sitemap.xml").write_text("\n".join(lines), encoding="utf-8")
    print(f"🗺️  sitemap.xml — {len(entries)} URLs → {PUBLIC}/sitemap.xml")


if __name__ == "__main__":
    build()
