#!/usr/bin/env python3
"""gen-team-pages.py — 48 隊靜態頁 /teams/<CODE>/index.html

每隊一頁，內容：
  - 國旗 + 隊名 + 分組
  - 3 場小組賽（台北時間 + 當地 ET + 場館 + 主客 + 單場 Google Calendar）
  - 訂閱（webcal）/ 下載（.ics）CTA
  - canonical / OG 七件套 / GA4 / SportsTeam + ItemList(SportsEvent) JSON-LD
  - 非官方 disclaimer

同時修掉 ICS DESCRIPTION 連到 /teams/<CODE>/ 的 404（gen-ics.py 已指向此頁）。

設計 token 沿用 build-articles（單一來源，避免 drift）。
時間顯示一律 normalize，不 leak raw `03:00+1`（[[feedback_internal_token_leak_to_user_display]]）。

用法：python3 scripts/gen-team-pages.py
"""

import importlib.util
import html as html_lib
import json
import pathlib
import urllib.parse
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

# ---- 沿用 build-articles 的共用 design tokens + JSON-LD helpers ----
_spec = importlib.util.spec_from_file_location("build_articles", ROOT / "scripts" / "build-articles.py")
ba = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ba)

GA_SNIPPET = ba.GA_SNIPPET
SHARED_TOKENS_CSS = ba.SHARED_TOKENS_CSS
THEME_SWITCH_CSS = ba.THEME_SWITCH_CSS
THEME_SWITCH_HTML = ba.THEME_SWITCH_HTML
THEME_SWITCH_JS = ba.THEME_SWITCH_JS
SITE_HEADER_CSS = ba.SITE_HEADER_CSS
site_header_html = ba.site_header_html
DISCLAIMER_HTML = ba.DISCLAIMER_HTML
graph_ld = ba.graph_ld
org_node = ba.org_node
website_node = ba.website_node
tournament_node = ba.tournament_node
breadcrumb_node = ba.breadcrumb_node

SITE = "https://foootball.twtools.cc"
WK = ["一", "二", "三", "四", "五", "六", "日"]


def esc(s) -> str:
    return html_lib.escape(str(s if s is not None else ""))


def taipei_parts(m):
    """('6/12（五）', '03:00', '2026-06-12') + ET ('6/11 15:00 ET') — 不 leak raw +1。"""
    raw = m["kickoff_taipei"]
    plus = 0
    if "+" in raw:
        raw, p = raw.split("+")
        plus = int(p)
    hh, mm = raw.split(":")
    base = datetime.strptime(m["date"], "%Y-%m-%d")
    tp = base + timedelta(days=plus)
    md = f"{tp.month}/{tp.day}（{WK[tp.weekday()]}）"
    time_str = f"{int(hh):02d}:{mm}"
    iso = f"{tp.strftime('%Y-%m-%d')}T{time_str}:00+08:00"
    et = f"{base.month}/{base.day} {m['kickoff_et']} ET"
    return md, time_str, iso, et


def gcal_link(m, zh):
    """單場 Google Calendar 連結（ET → UTC，與首頁 buildGCalLink 同邏輯）。"""
    hh, mm = (int(x) for x in m["kickoff_et"].split(":"))
    d = datetime.strptime(m["date"], "%Y-%m-%d") + timedelta(hours=hh + 4, minutes=mm)  # EDT→UTC
    start = d.strftime("%Y%m%dT%H%M%SZ")
    end = (d + timedelta(hours=2)).strftime("%Y%m%dT%H%M%SZ")
    home_zh = zh.get(m["home_code"], m["home_team"])
    away_zh = zh.get(m["away_code"], m["away_team"])
    md, time_str, _, et = taipei_parts(m)
    params = {
        "action": "TEMPLATE",
        "text": f"{home_zh} vs {away_zh} (Group {m['group']})",
        "dates": f"{start}/{end}",
        "details": (f"2026 FIFA 世界盃 Match #{m['match_no']} | Group {m['group']}\n"
                    f"台北時間：{md}{time_str}\n美加墨當地：{m['date']} {m['kickoff_et']} ET"),
        "location": f"{m['stadium']}, {m['city']}",
    }
    return "https://calendar.google.com/calendar/render?" + urllib.parse.urlencode(params)


TEAM_CSS = """
.container { max-width: 760px; margin: 0 auto; position: relative; z-index: 1; }
.tm-hero { display: flex; align-items: center; gap: 20px; margin: 8px 0 10px; }
.tm-flag { width: 88px; height: 66px; object-fit: cover; border-radius: 8px; box-shadow: 0 5px 16px var(--sheet-shadow); outline: 1px solid var(--line-2); outline-offset: -1px; flex-shrink: 0; }
.tm-head { display: flex; flex-direction: column; gap: 6px; }
.tm-kicker { font-family: var(--font-mono); font-size: 11px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--accent); font-weight: 600; }
.tm-title { font-family: var(--font-display); font-weight: 400; font-size: clamp(34px, 7vw, 52px); line-height: 1; color: var(--fg); letter-spacing: 0.5px; }
.tm-title .code { font-family: var(--font-mono); font-size: 0.4em; color: var(--accent); margin-left: 10px; letter-spacing: 1px; vertical-align: middle; }
.tm-sub { font-size: 14.5px; color: var(--fg-soft); line-height: 1.6; }
.tm-sub strong { color: var(--fg); font-weight: 700; }

.tm-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 26px 0 8px; }
@media (max-width: 480px) { .tm-actions { grid-template-columns: 1fr; } }
.tm-btn { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 15px 16px; border-radius: 12px; text-decoration: none; font-weight: 800; font-size: 14.5px; letter-spacing: 0.3px; transition: transform 0.18s cubic-bezier(0.22,1,0.36,1), background-color 0.18s ease, border-color 0.18s ease; }
.tm-btn-sub { background-color: var(--accent); color: var(--accent-ink); box-shadow: 0 10px 26px var(--accent-glow); }
.tm-btn-sub:hover { transform: translateY(-2px); background-color: var(--accent-bright); }
.tm-btn-dl { background: transparent; color: var(--fg); border: 1px solid var(--line-2); }
.tm-btn-dl:hover { transform: translateY(-2px); border-color: var(--fg-soft); background-color: var(--surface-3); }
.tm-hint { font-size: 11.5px; color: var(--faint); text-align: center; margin-bottom: 30px; line-height: 1.6; }

.tm-section-label { display: flex; align-items: center; gap: 12px; font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px; color: var(--dim); text-transform: uppercase; margin: 34px 0 16px; }
.tm-section-label::before { content: ''; width: 22px; height: 2px; background: var(--accent); }
.tm-section-label .rule { flex: 1; height: 1px; background: var(--line); }

.tm-match { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; margin-bottom: 11px; transition: border-color 0.18s ease, background 0.18s ease; }
.tm-match:hover { border-color: var(--line-2); background: var(--surface-2); }
.tm-when { text-align: center; min-width: 62px; }
.tm-time { font-family: var(--font-display); font-size: 23px; line-height: 1; color: var(--accent); letter-spacing: 0.5px; font-variant-numeric: tabular-nums; }
.tm-date { font-family: var(--font-mono); font-size: 10.5px; color: var(--dim); margin-top: 5px; }
.tm-et { font-family: var(--font-mono); font-size: 9.5px; color: var(--faint); margin-top: 2px; }
.tm-opp { min-width: 0; }
.tm-opp-top { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.tm-opp-vs { font-size: 11px; color: var(--faint); font-family: var(--font-mono); }
.tm-opp-flag { width: 22px; height: 16px; object-fit: cover; border-radius: 3px; outline: 1px solid var(--line-2); outline-offset: -1px; flex-shrink: 0; }
.tm-opp-name { font-size: 15.5px; font-weight: 700; color: var(--fg); }
.tm-tag { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 1px; padding: 2px 7px; border-radius: 5px; border: 1px solid var(--line-2); color: var(--dim); }
.tm-tag.home { color: var(--accent); border-color: var(--accent-line); }
.tm-venue { font-size: 12px; color: var(--dim); margin-top: 5px; }
.tm-gcal { background: var(--surface-3); color: var(--fg-soft); border: 1px solid var(--line-2); padding: 9px 13px; border-radius: 9px; font-size: 12px; font-weight: 600; text-decoration: none; white-space: nowrap; transition: background-color 0.16s ease, color 0.16s ease, border-color 0.16s ease; }
.tm-gcal:hover { background-color: var(--accent); color: var(--accent-ink); border-color: var(--accent); }

.tm-footer { margin-top: 50px; padding-top: 26px; border-top: 1px solid var(--line); text-align: center; }
.tm-foot-cta { font-size: 14.5px; color: var(--fg); margin-bottom: 12px; }
.tm-foot-cta a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-line); }
.tm-foot-links { font-family: var(--font-mono); font-size: 12px; letter-spacing: 1px; margin-bottom: 10px; }
.tm-foot-links a { color: var(--dim); text-decoration: none; }
.tm-foot-links a:hover { color: var(--accent); }
.tm-foot-fine { font-size: 11px; color: var(--faint); line-height: 1.6; }
"""


def render_team(team, matches, zh, iso_by_code, updated_disp, updated_iso):
    code = team["code"]
    name_zh = team["name_zh"]
    name_en = team.get("name_en", code)
    group = team["group"]
    flag = f"https://flagcdn.com/w160/{team['iso']}.png"
    page_url = f"{SITE}/teams/{code}/"
    ics_url = f"{SITE}/cal/{code}.ics"
    webcal_url = ics_url.replace("https:", "webcal:")
    og_img = f"{SITE}/cards/{code}.png"

    # 賽程列 + SportsEvent JSON-LD
    rows = []
    events = []
    for m in matches:
        is_home = m["home_code"] == code
        opp_code = m["away_code"] if is_home else m["home_code"]
        opp_zh = zh.get(opp_code, opp_code)
        opp_iso = m["away_iso"] if is_home else m["home_iso"]
        md, time_str, iso_dt, et = taipei_parts(m)
        tag = '<span class="tm-tag home">主場</span>' if is_home else '<span class="tm-tag">客場</span>'
        rows.append(
            '<div class="tm-match">'
            f'<div class="tm-when"><div class="tm-time">{esc(time_str)}</div>'
            f'<div class="tm-date">{esc(md)}</div><div class="tm-et">{esc(et)}</div></div>'
            '<div class="tm-opp"><div class="tm-opp-top">'
            '<span class="tm-opp-vs">VS</span>'
            f'<img class="tm-opp-flag" src="https://flagcdn.com/w160/{esc(opp_iso)}.png" alt="{esc(opp_zh)} 國旗" loading="lazy">'
            f'<span class="tm-opp-name">{esc(opp_zh)}</span>{tag}</div>'
            f'<div class="tm-venue">{esc(m["stadium"])}, {esc(m["city"])}</div></div>'
            f'<a class="tm-gcal" href="{esc(gcal_link(m, zh))}" target="_blank" rel="noopener">Google</a>'
            '</div>'
        )
        home_zh = zh.get(m["home_code"], m["home_team"])
        away_zh = zh.get(m["away_code"], m["away_team"])
        events.append({
            "@type": "SportsEvent",
            "name": f"{home_zh} vs {away_zh}（Group {m['group']}）",
            "sport": "Soccer",
            "startDate": iso_dt,
            "eventStatus": "https://schema.org/EventScheduled",
            "location": {"@type": "Place", "name": f"{m['stadium']}, {m['city']}"},
            "competitor": [
                {"@type": "SportsTeam", "name": home_zh},
                {"@type": "SportsTeam", "name": away_zh},
            ],
            "superEvent": {"@id": f"{SITE}/#worldcup2026"},
        })

    team_ld = {
        "@type": "SportsTeam",
        "@id": f"{page_url}#team",
        "name": name_zh,
        "alternateName": name_en,
        "sport": "Soccer",
        "url": page_url,
        "logo": flag,
        "memberOf": {"@id": f"{SITE}/#worldcup2026"},
    }
    item_list = {
        "@type": "ItemList",
        "name": f"{name_zh} 2026 世界盃小組賽賽程",
        "numberOfItems": len(events),
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "item": ev}
            for i, ev in enumerate(events)
        ],
    }
    crumb = breadcrumb_node([
        ("首頁", f"{SITE}/"),
        ("球隊賽程", f"{SITE}/teams/"),
        (name_zh, page_url),
    ])
    webpage_ld = {
        "@type": "WebPage", "@id": page_url, "url": page_url,
        "name": f"{name_zh} 2026 世界盃賽程",
        "inLanguage": "zh-Hant", "isPartOf": {"@id": f"{SITE}/#website"},
        "primaryImageOfPage": og_img,
    }
    if updated_iso:
        webpage_ld["dateModified"] = updated_iso
    jsonld = graph_ld([org_node(), website_node(), tournament_node(),
                       team_ld, item_list, webpage_ld, crumb])

    title = f"{name_zh} 2026 世界盃賽程"
    desc = (f"{name_zh}（{name_en}）2026 美加墨世界盃 {group} 組完整小組賽賽程：對手、台北時間、"
            f"場館，一鍵訂閱進 Apple／Google 行事曆。")
    updated_line = f"最後更新：{updated_disp} 台北時間 · " if updated_disp else ""

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="grass">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}｜{esc(group)} 組 · 對手與台北時間 @foootball</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
{jsonld}
<meta property="og:type" content="website">
<meta property="og:url" content="{page_url}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{og_img}">
<meta property="og:image:width" content="1080">
<meta property="og:image:height" content="1350">
<meta property="og:site_name" content="@foootball">
<meta property="og:locale" content="zh_TW">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{og_img}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{GA_SNIPPET}
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{TEAM_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">
{site_header_html('home')}
  <div class="tm-hero">
    <img class="tm-flag" src="{flag}" alt="{esc(name_zh)} 國旗">
    <div class="tm-head">
      <div class="tm-kicker">2026 FIFA WORLD CUP · GROUP {esc(group)}</div>
      <h1 class="tm-title">{esc(name_zh)}<span class="code">{esc(code)}</span></h1>
      <div class="tm-sub"><strong>{esc(group)} 組</strong> · 3 場小組賽 · 全程台北時間自動換算</div>
    </div>
  </div>

  <div class="tm-actions">
    <a class="tm-btn tm-btn-sub" href="{webcal_url}">📅 訂閱 {esc(name_zh)} 賽程</a>
    <a class="tm-btn tm-btn-dl" href="{ics_url}" download="{esc(code)}.ics">⬇️ 下載 .ics</a>
  </div>
  <div class="tm-hint">Apple Calendar 一鍵訂閱自動同步（含淘汰賽）· Google Calendar 桌機貼上 URL · 下載為單次匯入</div>

  <div class="tm-section-label">小組賽賽程 <span class="rule"></span></div>
{chr(10).join(rows)}

  <div class="tm-footer">
    <div class="tm-foot-cta">看完整 12 組積分與戰況：<a href="/standings/">戰況中心</a> · 每日戰報：<a href="/articles/">/articles/</a></div>
    <div class="tm-foot-links"><a href="/">全部 48 隊</a> · <a href="/standings/">戰況</a> · <a href="https://medium.com/@foootball" target="_blank" rel="noopener">Medium ↗</a></div>
    <div class="tm-foot-fine">{updated_line}賽程資料整理自公開來源 · 時間為台北時間（北美場次標註當地 ET）</div>
    {DISCLAIMER_HTML}
  </div>
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


def last_updated_taipei():
    p = PUBLIC / "fixtures-data.json"
    if not p.exists():
        return "", ""
    tp = datetime.utcfromtimestamp(p.stat().st_mtime) + timedelta(hours=8)
    return tp.strftime("%Y-%m-%d %H:%M"), tp.strftime("%Y-%m-%d")


def render_index(teams_sorted, zh):
    """/teams/ 索引頁 — 12 組 grid，連到各隊頁（也餵 sitemap / breadcrumb root）。"""
    by_group = {}
    for t in teams_sorted:
        by_group.setdefault(t["group"], []).append(t)
    blocks = []
    for g in sorted(by_group):
        cards = "".join(
            f'<a class="ti-card" href="/teams/{esc(t["code"])}/">'
            f'<img class="ti-flag" src="https://flagcdn.com/w160/{esc(t["iso"])}.png" alt="{esc(t["name_zh"])} 國旗" loading="lazy">'
            f'<span class="ti-name">{esc(t["name_zh"])}</span>'
            f'<span class="ti-code">{esc(t["code"])}</span></a>'
            for t in by_group[g]
        )
        blocks.append(
            f'<section class="ti-group"><h2 class="ti-group-h">'
            f'<span class="ti-group-tag">Group</span>{esc(g)}</h2>'
            f'<div class="ti-grid">{cards}</div></section>'
        )
    groups_html = "".join(blocks)

    crumb = breadcrumb_node([("首頁", f"{SITE}/"), ("球隊賽程", f"{SITE}/teams/")])
    item_list = {
        "@type": "ItemList",
        "name": "2026 世界盃 48 隊賽程頁",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": f"{SITE}/teams/{t['code']}/", "name": t["name_zh"]}
            for i, t in enumerate(teams_sorted)
        ],
    }
    collection = {
        "@type": "CollectionPage", "@id": f"{SITE}/teams/", "url": f"{SITE}/teams/",
        "name": "球隊賽程 — 2026 世界盃 48 隊", "inLanguage": "zh-Hant",
        "isPartOf": {"@id": f"{SITE}/#website"}, "mainEntity": item_list,
    }
    jsonld = graph_ld([org_node(), website_node(), tournament_node(), collection, crumb])

    title = "球隊賽程 — 2026 世界盃 48 隊"
    desc = "2026 美加墨世界盃 48 支國家隊，每隊一頁完整小組賽賽程（台北時間）與一鍵行事曆訂閱。"
    ti_css = """
.container { max-width: 1000px; margin: 0 auto; position: relative; z-index: 1; }
.ti-h1 { font-family: var(--font-display); font-weight: 400; font-size: clamp(30px, 5vw, 46px); line-height: 1.1; color: var(--fg); letter-spacing: 0.4px; margin: 6px 0 8px; }
.ti-intro { font-size: 14px; color: var(--fg-soft); margin-bottom: 36px; }
.ti-group { margin-bottom: 30px; }
.ti-group-h { font-family: var(--font-display); font-weight: 400; font-size: 24px; color: var(--accent); letter-spacing: 1px; display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.ti-group-tag { font-family: var(--font-mono); font-size: 10px; letter-spacing: 2px; color: var(--dim); text-transform: uppercase; }
.ti-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 11px; }
@media (max-width: 640px) { .ti-grid { grid-template-columns: repeat(2, 1fr); } }
.ti-card { display: flex; flex-direction: column; align-items: center; gap: 7px; text-align: center; text-decoration: none; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 16px 10px 13px; transition: transform 0.2s cubic-bezier(0.22,1,0.36,1), border-color 0.2s ease, background 0.2s ease; }
.ti-card:hover { transform: translateY(-3px); border-color: var(--accent-line); background: var(--surface-2); }
.ti-flag { width: 54px; height: 40px; object-fit: cover; border-radius: 5px; box-shadow: 0 3px 9px var(--sheet-shadow); outline: 1px solid var(--line-2); outline-offset: -1px; }
.ti-name { font-size: 14.5px; font-weight: 700; color: var(--fg); }
.ti-code { font-family: var(--font-mono); font-size: 10px; color: var(--dim); letter-spacing: 1.5px; }
.ti-footer { margin-top: 44px; padding-top: 24px; border-top: 1px solid var(--line); text-align: center; }
"""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="grass">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)} @foootball</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{SITE}/teams/">
{jsonld}
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE}/teams/">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{SITE}/og-home.png">
<meta property="og:image:width" content="2400">
<meta property="og:image:height" content="1260">
<meta property="og:site_name" content="@foootball">
<meta property="og:locale" content="zh_TW">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{SITE}/og-home.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{GA_SNIPPET}
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{ti_css}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">
{site_header_html('home')}
  <h1 class="ti-h1">球隊賽程 · 48 隊</h1>
  <div class="ti-intro">點你的國家隊看完整小組賽賽程（台北時間）與一鍵行事曆訂閱。</div>
  {groups_html}
  <footer class="ti-footer">{DISCLAIMER_HTML}</footer>
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


def build():
    fd = json.loads((PUBLIC / "fixtures-data.json").read_text(encoding="utf-8"))
    teams = fd["teams"]
    zh = fd["team_zh"]
    iso_by_code = {t["code"]: t["iso"] for t in teams}
    matches = fd["matches"]
    updated_disp, updated_iso = last_updated_taipei()

    by_team = {}
    for m in matches:
        for c in (m["home_code"], m["away_code"]):
            by_team.setdefault(c, []).append(m)

    teams_sorted = sorted(teams, key=lambda t: (t["group"], t["name_zh"]))
    out_root = PUBLIC / "teams"
    out_root.mkdir(parents=True, exist_ok=True)

    n = 0
    for t in teams_sorted:
        tm = sorted(by_team.get(t["code"], []),
                    key=lambda m: (m["date"], m["kickoff_taipei"]))
        out_dir = out_root / t["code"]
        out_dir.mkdir(parents=True, exist_ok=True)
        html = render_team(t, tm, zh, iso_by_code, updated_disp, updated_iso)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        n += 1

    (out_root / "index.html").write_text(render_index(teams_sorted, zh), encoding="utf-8")
    print(f"✅ {n} 隊頁 + /teams/index.html → {out_root}")


if __name__ == "__main__":
    build()
