#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-baseball-team-pages.py — MLB 球隊頁 + 球隊目錄(public-baseball/teams/).

每隊一頁:戰績摘要(W-L/勝率/分區排名/勝差/連勝敗/得失分)+ 主客場拆分 + 球員名冊(背號/守位)。
資料全走官方免費 MLB StatsAPI(乾淨例行賽,非 api-baseball 的春訓+季後賽灌水版)。每頁帶
SportsTeam JSON-LD(AEO 實體)。版型沿用 build-articles 的共用外殼 + baseball(navy/@BASEBALL)
站身分,與文章頁同系列。

用法:python3 scripts/gen-baseball-team-pages.py [--season 2024]
"""
import argparse
import datetime
import html as html_lib
import importlib.util
import pathlib
import re
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ba = _load("build_articles", "build-articles.py")
bs = _load("build_standings", "build-standings.py")
mp = _load("fetch_mlb_players", "fetch-mlb-players.py")

SITE = ba.SITES.get("baseball")
BASE = SITE["base"]

POS_ZH = {"P": "投手", "C": "捕手", "1B": "一壘手", "2B": "二壘手", "3B": "三壘手",
          "SS": "游擊手", "LF": "左外野", "CF": "中外野", "RF": "右外野", "OF": "外野手",
          "DH": "指定打擊", "TWP": "投打二刀流"}
POS_ORDER = {"P": 0, "C": 1, "1B": 2, "2B": 3, "3B": 4, "SS": 5,
             "LF": 6, "CF": 7, "RF": 8, "OF": 9, "DH": 10, "TWP": 11}

TEAM_CSS = """
.bt-h1 { font-family: var(--font-display); font-size: clamp(30px,5vw,46px); line-height:1.1; margin: 4px 0 6px; }
.bt-en { color: var(--dim); font-size: 15px; letter-spacing:1px; }
.bt-sub { color: var(--fg-soft); font-size: 15px; margin: 10px 0 30px; }
.bt-sub b { color: var(--accent); }
.std-table { width:100%; border-collapse:collapse; margin: 14px 0 30px; font-size: 14.5px; }
.std-table th, .std-table td { padding: 9px 8px; text-align:center; border-bottom:1px solid var(--line); }
.std-table th { color: var(--dim); font-weight:600; font-size:12.5px; }
.std-table td.l, .std-table th.l { text-align:left; }
.std-pts { color: var(--accent); font-weight:800; }
.bt-sec { font-family:var(--font-mono); font-size:12px; letter-spacing:2px; color:var(--dim); text-transform:uppercase; margin: 26px 0 6px; }
.bt-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px 22px; margin: 10px 0 30px; }
.bt-grid .r { display:flex; gap:10px; align-items:baseline; padding:7px 4px; border-bottom:1px solid var(--line); }
.bt-grid .num { font-family:var(--font-mono); color:var(--accent); min-width:30px; font-size:13px; }
.bt-grid .nm { flex:1; font-size:14.5px; }
.bt-grid .ps { color:var(--dim); font-size:12.5px; }
.idx-teams { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; margin:10px 0 26px; }
.idx-teams a { display:block; padding:13px 15px; border:1px solid var(--line); border-radius:10px; text-decoration:none; color:var(--fg); transition:border-color .15s; }
.idx-teams a:hover { border-color: var(--accent-line); }
.idx-teams .z { font-weight:700; }
.idx-teams .e { color:var(--dim); font-size:12px; }
.bt-asof { color:var(--dim); font-size:12.5px; line-height:1.6; margin: 26px 0 8px; border-top:1px solid var(--line); padding-top:14px; }
"""


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
{ba.GA_SNIPPET}
<style>
{ba.SHARED_TOKENS_CSS}{ba.extra_theme_css(SITE)}
{ba.THEME_SWITCH_CSS}
{ba.SITE_HEADER_CSS}
{TEAM_CSS}
</style>
</head>
<body>
{ba.theme_switch_html(SITE)}
<div class="container">{ba.site_header_html('home', SITE)}
{body}
{ba.site_footer_html(SITE)}
</div>
<script>{ba.theme_switch_js(SITE)}</script>
</body>
</html>
"""


def _zh(name):
    return bs.TEAM_ZH.get(bs._norm_name(name), name)


def render_team(team, rec, roster, season, asof):
    en = team["name"]
    zh = _zh(en)
    slug = team["abbr"].lower()
    canonical = f"{BASE}/teams/{slug}/"
    w, l = rec["wins"], rec["losses"]
    rd = rec["run_diff"]
    rd_s = f"+{rd}" if isinstance(rd, int) and rd > 0 else str(rd)
    rec_table = (
        '<table class="std-table"><thead><tr>'
        '<th>勝</th><th>敗</th><th>勝率</th><th>分區</th><th>分區排名</th>'
        '<th>勝差</th><th>近況</th><th>得分</th><th>失分</th><th>淨</th>'
        '</tr></thead><tbody><tr>'
        f'<td class="std-pts">{w}</td><td>{l}</td><td>{rec["pct"]}</td>'
        f'<td>{rec["division_zh"]}</td><td>{rec["division_rank"]}</td>'
        f'<td>{rec["games_back"]}</td><td>{rec["streak"]}</td>'
        f'<td>{rec["runs_scored"]}</td><td>{rec["runs_allowed"]}</td><td>{rd_s}</td>'
        '</tr></tbody></table>'
    )
    split_table = (
        '<div class="bt-sec">主客場拆分</div>'
        '<table class="std-table"><thead><tr><th class="l">場地</th><th>勝</th><th>敗</th></tr></thead><tbody>'
        f'<tr><td class="l">主場</td><td class="std-pts">{rec["home_wins"]}</td><td>{rec["home_losses"]}</td></tr>'
        f'<tr><td class="l">客場</td><td class="std-pts">{rec["away_wins"]}</td><td>{rec["away_losses"]}</td></tr>'
        '</tbody></table>'
    )
    rs = sorted(roster, key=lambda p: (POS_ORDER.get(p["position"], 99),
                                       int(p["number"]) if str(p["number"]).isdigit() else 999))
    rows = ""
    for p in rs:
        pz = POS_ZH.get(p["position"], p["position"])
        rows += (f'<div class="r"><span class="num">{html_lib.escape(str(p["number"]))}</span>'
                 f'<span class="nm">{html_lib.escape(p["name"])}</span>'
                 f'<span class="ps">{pz}</span></div>')
    roster_block = (f'<div class="bt-sec">球員名冊 · {len(rs)} 人</div>'
                    f'<div class="bt-grid">{rows}</div>') if rs else ""

    team_node = {
        "@type": "SportsTeam", "@id": f"{canonical}#team", "name": zh,
        "alternateName": en, "sport": "Baseball", "url": canonical,
        "memberOf": {"@type": "SportsOrganization", "@id": f"{BASE}/#league-mlb",
                     "name": "美國職棒大聯盟"},
    }
    crumb = ba.breadcrumb_node([("首頁", f"{BASE}/"), ("球隊", f"{BASE}/teams/"), (zh, canonical)])
    jsonld = ba.graph_ld([ba.org_node(SITE), ba.website_node(SITE), team_node, crumb])
    asof_note = (f'<p class="bt-asof">資料來源：MLB 官方 StatsAPI；{season} 賽季例行賽，'
                 f'截至 {asof}，賽季進行中、戰績與名冊逐日更新。</p>')
    body = (f'<h1 class="bt-h1">{html_lib.escape(zh)}</h1>'
            f'<div class="bt-en">{html_lib.escape(en)}</div>'
            f'<div class="bt-sub">{rec["division_zh"]} · {season} 賽季例行賽 <b>{w}-{l}</b>'
            f'（勝率 {rec["pct"]}，分區第 {rec["division_rank"]}；截至 {asof}）</div>'
            f'{rec_table}{split_table}{roster_block}{asof_note}')
    desc = f"{zh}（{en}）MLB 球隊資料：{season} 賽季例行賽 {w}-{l}（截至 {asof}）、{rec['division_zh']}、球員名冊與主客場戰績。"
    return slug, _shell(f"{zh} {en}｜{season} 球隊資料", desc, canonical, jsonld, body)


def render_index(teams, season, asof):
    by_div = {}
    for t in teams:
        by_div.setdefault(t["_rec"]["division_zh"], []).append(t)
    order = ["美聯東區", "美聯中區", "美聯西區", "國聯東區", "國聯中區", "國聯西區"]
    blocks = ""
    for dv in order:
        items = sorted(by_div.get(dv, []), key=lambda t: t["_rec"]["division_rank"])
        if not items:
            continue
        cards = ""
        for t in items:
            zh = _zh(t["name"])
            cards += (f'<a href="/teams/{t["abbr"].lower()}/"><span class="z">{html_lib.escape(zh)}</span>'
                      f'<br><span class="e">{html_lib.escape(t["name"])} · {t["_rec"]["wins"]}-{t["_rec"]["losses"]}</span></a>')
        blocks += f'<div class="bt-sec">{dv}</div><div class="idx-teams">{cards}</div>'
    canonical = f"{BASE}/teams/"
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": "MLB 球隊", "inLanguage": "zh-Hant", "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = ba.graph_ld([ba.org_node(SITE), ba.website_node(SITE), coll,
                          ba.breadcrumb_node([("首頁", f"{BASE}/"), ("球隊", canonical)])])
    body = ('<h1 class="bt-h1">MLB 球隊</h1>'
            f'<div class="bt-sub">美國職棒大聯盟 30 隊 · {season} 賽季例行賽戰績、名冊與主客場資料（截至 {asof}，賽季進行中）。</div>'
            f'{blocks}'
            f'<p class="bt-asof">資料來源：MLB 官方 StatsAPI；{season} 賽季例行賽，截至 {asof}，賽季進行中、數字逐日更新。</p>')
    return _shell(f"MLB 球隊資料（{season}）", f"美國職棒大聯盟 30 隊 {season} 賽季戰績、球員名冊與主客場資料（截至 {asof}）。",
                  canonical, jsonld, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--asof", default=datetime.date.today().isoformat(),
                    help="資料截點顯示日（預設今天）")
    args = ap.parse_args()
    asof = args.asof

    print(f"📡 MLB teams {args.season} (StatsAPI) …")
    teams = mp.teams(args.season)
    recs = {r["team_id"]: r for r in mp.team_records(args.season)}
    out_root = ROOT / "public-baseball" / "teams"
    out_root.mkdir(parents=True, exist_ok=True)

    rendered = []
    for t in teams:
        rec = recs.get(t["id"])
        if not rec:
            print(f"   ⚠️ no record for {t['name']}"); continue
        roster = mp.roster(t["id"], args.season)
        time.sleep(0.25)
        slug, html = render_team(t, rec, roster, args.season, asof)
        d = out_root / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(html, encoding="utf-8")
        t["_rec"] = rec
        rendered.append(t)
        print(f"   ✅ {slug}  {_zh(t['name'])}  {rec['wins']}-{rec['losses']}  名冊 {len(roster)}")

    (out_root / "index.html").write_text(render_index(rendered, args.season, asof), encoding="utf-8")
    print(f"📚 teams/index.html ({len(rendered)} teams) → {out_root}/")

    # 清掉孤兒球隊目錄（隊伍 abbr 跨季變動會留下舊頁，如 OAK→ATH），避免 stale 頁被訪問。
    live_slugs = {t["abbr"].lower() for t in rendered}
    import shutil
    for d in out_root.iterdir():
        if d.is_dir() and d.name not in live_slugs:
            shutil.rmtree(d)
            print(f"   🧹 removed orphan team dir: {d.name}")

    # merge team URLs into the site sitemap (keep landing + article URLs; replace teams block)
    sm = ROOT / "public-baseball" / "sitemap.xml"
    keep = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
            if "/teams/" not in u] if sm.exists() else [f"{BASE}/"]
    team_urls = [f"{BASE}/teams/"] + [f"{BASE}/teams/{t['abbr'].lower()}/" for t in rendered]
    urls = list(dict.fromkeys(keep + team_urls))
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                  f"{body}</urlset>\n", encoding="utf-8")
    print(f"🗺️  sitemap.xml → {len(urls)} URLs (+{len(team_urls)} teams)")


if __name__ == "__main__":
    main()
