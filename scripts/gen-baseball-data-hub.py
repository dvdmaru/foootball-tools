#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-baseball-data-hub.py — 數據總覽 hub 頁(public-baseball/data/).

nav「數據」的落地頁：把 MLB 排名/排行(/standings/)、MLB 球隊(/teams/)、中職 CPBL(/cpbl/)
三個既有數據頁集中分流(drill-down tiles)，並說明各聯盟的數據範圍。server-rendered，
沿用 build-articles 共用外殼 + baseball(navy/@BASEBALL)站身分，active nav = "data"。

⚠️ 跑序：build-articles.py 會整個覆寫 sitemap → 必須先 build-articles，再跑本腳本(re-merge /data/)。

用法：python3 scripts/gen-baseball-data-hub.py
"""
import html as html_lib
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ba = _load("build_articles", "build-articles.py")
SITE = ba.SITES.get("baseball")
BASE = SITE["base"]

# 數據頁清單：(href, icon, 標題, 說明)
DESTS = [
    ("/standings/", "📊", "MLB 排名與排行榜",
     "美國職棒大聯盟六分區戰績（勝負・勝率・勝差・淨分），加上打擊與投手數據排行榜（全壘打／打點／打擊率／盜壘／防禦率／三振／勝投／救援）。資料來自官方 MLB StatsAPI。"),
    ("/teams/", "⚾", "MLB 30 隊球隊資料",
     "30 支大聯盟球隊逐隊一頁：例行賽戰績、主客場拆分、球員名冊與分區排名。"),
    ("/cpbl/", "🇹🇼", "中職 CPBL 戰績與排行",
     "中華職棒 6 隊戰績與投打 TOP5。資料為 cpbl.com.tw 官方首頁人工擷取快照（非即時），頁面標註擷取日期。"),
]


def _shell(title, desc, canonical, jsonld, body):
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="{SITE['default_theme']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)} | {SITE['title_suffix']}</title>
<meta name="description" content="{html_lib.escape(desc)}">
<meta property="og:title" content="{html_lib.escape(title)}">
<meta property="og:description" content="{html_lib.escape(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="{SITE['org_name']}">
<meta property="og:locale" content="zh_TW">
<link rel="canonical" href="{canonical}">
{jsonld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{ba.ga_snippet(SITE)}
<style>
{ba.SHARED_TOKENS_CSS}{ba.extra_theme_css(SITE)}
{ba.SITE_HEADER_CSS}
{ba.BB_LANDING_CSS}
{ba.BB_DASH_CSS}
.hub-grid{{display:grid;gap:14px;margin-top:6px}}
.hub-card{{display:flex;align-items:flex-start;gap:16px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius-sm);padding:20px 22px;text-decoration:none;color:var(--fg);transition:border-color .15s,transform .15s}}
.hub-card:hover{{border-color:var(--accent);transform:translateY(-2px)}}
.hub-card .ic{{font-size:30px;line-height:1}}
.hub-card .tt{{display:block;font-size:19px;font-weight:800;color:var(--fg)}}
.hub-card .dd{{display:block;font-size:14px;color:var(--fg-soft);line-height:1.65;margin-top:6px}}
.hub-card .go{{margin-left:auto;color:var(--accent);font-weight:800;align-self:center;font-size:15px}}
</style>
</head>
<body>
<div class="bb-shell">{ba.site_header_html('data', SITE)}
<main>
{body}
</main>
{ba._bb_footer(SITE)}
</div>
</body>
</html>
"""


def build_page():
    cards = ""
    for href, ic, tt, dd in DESTS:
        cards += (f'<a class="hub-card" href="{href}"><span class="ic">{ic}</span>'
                  f'<span><span class="tt">{html_lib.escape(tt)}</span>'
                  f'<span class="dd">{html_lib.escape(dd)}</span></span>'
                  f'<span class="go">→</span></a>')
    body = f"""<section class="bb-hero" style="padding-bottom:6px">
    <h1>數據總覽</h1>
    <p>四聯盟戰績與數據的入口。即時概覽看<a href="/" style="color:var(--accent)">首頁儀表板</a>；要逐隊、完整排行與中職細項，從下方進入。日職 NPB／韓職 KBO 的戰績與賽果目前彙整於首頁儀表板。</p>
  </section>
  <div class="bb-sec"><h2>數據頁</h2><span class="ln"></span></div>
  <div class="hub-grid">{cards}</div>"""
    canonical = f"{BASE}/data/"
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": "數據總覽", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = ba.graph_ld([ba.org_node(SITE), ba.website_node(SITE), coll,
                          ba.breadcrumb_node([("首頁", f"{BASE}/"), ("數據", canonical)])])
    desc = ("@baseball 數據總覽：MLB 排名與打投排行榜、MLB 30 隊球隊資料、中職 CPBL 戰績與 TOP5。"
            "四聯盟即時概覽見首頁儀表板。")
    return _shell("數據總覽", desc, canonical, jsonld, body)


def main():
    out_dir = ROOT / "public-baseball" / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_page(), encoding="utf-8")
    print("✅ public-baseball/data/index.html")

    sm = ROOT / "public-baseball" / "sitemap.xml"
    keep = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
            if "/data/" not in u] if sm.exists() else [f"{BASE}/"]
    urls = list(dict.fromkeys(keep + [f"{BASE}/data/"]))
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                  f"{body}</urlset>\n", encoding="utf-8")
    print(f"🗺️  sitemap.xml → {len(urls)} URLs (+/data/)")


if __name__ == "__main__":
    main()
