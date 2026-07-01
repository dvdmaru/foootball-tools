#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-baseball-standings.py — MLB 排名 + 數據排行榜 hub 頁(public-baseball/standings/).

單一頁 /standings/,三個 server-rendered HTML 區塊(CSS-only tabs,無 JS data fetch →
crawler 看得到全部表格,對齊 HTML-over-PNG for GEO 房規):
  · 分區排名:6 分區(美聯東/中/西、國聯東/中/西)官方例行賽戰績(排名/勝/負/勝率/勝差/近況/得失分/淨)
  · 打擊榜:全壘打/打點/打擊率/盜壘/OPS/安打/得分/二壘打 前 10
  · 投手榜:自責分率/三振/勝投/救援/WHIP 前 10

資料全走官方免費 MLB StatsAPI(乾淨例行賽)。2026 是賽季進行中的 live 資料、逐時 drift →
本頁本質是定期重生的 living page,標 as-of + 漂移警語。分區排名走 build-facts.team_records_asof
(date-pinned + name_zh + 同勝率並列偵測),排行榜讀 leagues/mlb-leaders-<season>.json。
版型沿用 build-articles 共用外殼 + baseball(navy/@BASEBALL)站身分,與球隊頁/文章頁同系列。

用法:
  python3 scripts/fetch-mlb-players.py leaders --season 2026   # 先產 leagues/mlb-leaders-2026.json
  python3 scripts/gen-baseball-standings.py [--season 2026] [--asof YYYY-MM-DD]
⚠️ 跑序:build-articles.py 會整個覆寫 sitemap → 必須先 build-articles,再跑 team-pages + 本腳本。
"""
import argparse
import datetime
import html as html_lib
import importlib.util
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ba = _load("build_articles", "build-articles.py")
bs = _load("build_standings", "build-standings.py")
mp = _load("fetch_mlb_players", "fetch-mlb-players.py")
bf = _load("build_facts", "build-facts.py")

SITE = ba.SITES.get("baseball")
BASE = SITE["base"]

DIV_ORDER = ["美聯東區", "美聯中區", "美聯西區", "國聯東區", "國聯中區", "國聯西區"]

STD_CSS = """
.st-h1 { font-family: var(--font-display); font-size: clamp(30px,5vw,46px); line-height:1.1; margin: 4px 0 6px; }
.st-sub { color: var(--fg-soft); font-size: 15px; margin: 10px 0 22px; }
.st-sub b { color: var(--accent); }
/* CSS-only tabs: radios drive panel visibility, no JS */
.tabs > input[name="bbtab"] { position:absolute; opacity:0; width:0; height:0; }
.tablabels { display:flex; flex-wrap:wrap; gap:8px; margin: 8px 0 22px; border-bottom:1px solid var(--line); }
.tablabels label { cursor:pointer; padding:9px 16px; font-size:14.5px; font-weight:700; color:var(--dim);
  border-bottom:2px solid transparent; margin-bottom:-1px; transition:color .15s, border-color .15s; }
.tablabels label:hover { color: var(--fg); }
.panel { display:none; }
#bbtab-div:checked ~ .tablabels label[for="bbtab-div"],
#bbtab-bat:checked ~ .tablabels label[for="bbtab-bat"],
#bbtab-pit:checked ~ .tablabels label[for="bbtab-pit"] { color: var(--accent); border-bottom-color: var(--accent); }
#bbtab-div:checked ~ .panel-div,
#bbtab-bat:checked ~ .panel-bat,
#bbtab-pit:checked ~ .panel-pit { display:block; }
.div-name { font-family:var(--font-mono); font-size:12.5px; letter-spacing:2px; color:var(--accent);
  text-transform:uppercase; margin: 24px 0 4px; font-weight:700; }
.div-tie { color:var(--dim); font-size:12px; margin: 2px 0 0; }
.std-table { width:100%; border-collapse:collapse; margin: 8px 0 14px; font-size: 14px; }
.std-table th, .std-table td { padding: 8px 6px; text-align:center; border-bottom:1px solid var(--line); white-space:nowrap; }
.std-table th { color: var(--dim); font-weight:600; font-size:12px; }
.std-table td.l, .std-table th.l { text-align:left; white-space:normal; }
.std-table td.rk { color:var(--dim); font-family:var(--font-mono); font-size:12.5px; }
.std-table tr.lead td.tm { font-weight:800; }
.std-pts { color: var(--accent); font-weight:800; }
.rd-pos { color:#5fb878; } .rd-neg { color:#d98a8a; }
.lb-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:8px 22px; margin: 10px 0 18px; }
.lb-card { border:1px solid var(--line); border-radius:12px; padding:12px 14px 8px; }
.lb-card h3 { font-size:14px; margin:0 0 6px; color:var(--fg); display:flex; justify-content:space-between; align-items:baseline; }
.lb-card h3 .u { color:var(--dim); font-size:11px; font-weight:500; letter-spacing:1px; }
.lb-card table { width:100%; border-collapse:collapse; font-size:13px; }
.lb-card td { padding:4px 2px; border-bottom:1px solid var(--line); }
.lb-card tr:last-child td { border-bottom:none; }
.lb-card td.rk { color:var(--dim); font-family:var(--font-mono); width:22px; }
.lb-card td.nm { text-align:left; }
.lb-card td.tm { color:var(--dim); font-size:11.5px; text-align:right; }
.lb-card td.vl { text-align:right; color:var(--accent); font-weight:800; font-family:var(--font-mono); width:54px; }
.st-asof { color:var(--dim); font-size:12.5px; line-height:1.6; margin: 24px 0 8px; border-top:1px solid var(--line); padding-top:14px; }
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
{ba.ga_snippet(SITE)}
<style>
{ba.SHARED_TOKENS_CSS}{ba.extra_theme_css(SITE)}
{ba.THEME_SWITCH_CSS}
{ba.SITE_HEADER_CSS}
{STD_CSS}
</style>
</head>
<body>
{ba.theme_switch_html(SITE)}
<div class="container">{ba.site_header_html('data', SITE)}
{body}
{ba.site_footer_html(SITE)}
</div>
<script>{ba.theme_switch_js(SITE)}</script>
</body>
</html>
"""


def _rd_span(rd):
    if not isinstance(rd, int):
        return str(rd)
    s = f"+{rd}" if rd > 0 else str(rd)
    cls = "rd-pos" if rd > 0 else ("rd-neg" if rd < 0 else "")
    return f'<span class="{cls}">{s}</span>' if cls else s


def render_division_tables(recs, ties, asof):
    by_div = {}
    for r in recs:
        by_div.setdefault(r["division_zh"], []).append(r)
    out = ['<div class="st-sub">美國職棒大聯盟 6 分區例行賽戰績，依官方分區排名排序'
           f'（截至 {asof}）。勝差(GB)、勝率採官方權威值。</div>']
    for dv in DIV_ORDER:
        teams = sorted(by_div.get(dv, []), key=lambda t: (t["division_rank"] or 99))
        if not teams:
            continue
        out.append(f'<div class="div-name">{dv}</div>')
        tie = ties.get(dv)
        if tie:
            names = "、".join(f'{x["name_zh"]}（{x["wins"]}-{x["losses"]}）' for x in tie["teams"])
            out.append(f'<p class="div-tie">⚖️ 並列首位（勝率 {tie["tied_pct"]}）：{names}；官方分區表依序暫列。</p>')
        rows = ""
        for t in teams:
            lead = ' class="lead"' if t["division_rank"] == 1 else ""
            rows += (
                f'<tr{lead}>'
                f'<td class="rk">{t["division_rank"]}</td>'
                f'<td class="l tm">{html_lib.escape(t["name_zh"])}</td>'
                f'<td class="std-pts">{t["wins"]}</td><td>{t["losses"]}</td>'
                f'<td>{t["pct"]}</td><td>{t["games_back"]}</td>'
                f'<td>{html_lib.escape(t["streak"] or "")}</td>'
                f'<td>{t["runs_scored"]}</td><td>{t["runs_allowed"]}</td>'
                f'<td>{_rd_span(t["run_diff"])}</td>'
                '</tr>'
            )
        out.append(
            '<table class="std-table"><thead><tr>'
            '<th class="rk">#</th><th class="l">球隊</th><th>勝</th><th>敗</th>'
            '<th>勝率</th><th>勝差</th><th>近況</th><th>得分</th><th>失分</th><th>淨勝分</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )
    return "\n".join(out)


def _zh(name):
    return bs.TEAM_ZH.get(bs._norm_name(name), name)


def render_leader_cards(board, cats):
    cards = []
    for c in cats:
        rows = board.get(c, [])
        if not rows:
            continue
        trs = ""
        for r in rows:
            trs += (f'<tr><td class="rk">{r.get("rank","")}</td>'
                    f'<td class="nm">{html_lib.escape(r.get("name",""))}</td>'
                    f'<td class="tm">{html_lib.escape(_zh(r.get("team","")))}</td>'
                    f'<td class="vl">{html_lib.escape(str(r.get("value","")))}</td></tr>')
        cards.append(
            f'<div class="lb-card"><h3>{mp.CAT_ZH.get(c, c)}</h3>'
            f'<table><tbody>{trs}</tbody></table></div>'
        )
    return f'<div class="lb-grid">{"".join(cards)}</div>'


def build_page(recs, ties, leaders, season, asof):
    canonical = f"{BASE}/standings/"
    div_panel = render_division_tables(recs, ties, asof)
    bat_panel = ('<div class="st-sub">打擊數據前 10（全壘打 / 打點 / 打擊率 / 盜壘 / OPS / 安打 / 得分 / 二壘打）。'
                 '率定數（打擊率、OPS）已套官方規定打席門檻，榜上皆合格者。</div>'
                 + render_leader_cards(leaders.get("hitting", {}), mp.HITTING_CATS))
    pit_panel = ('<div class="st-sub">投手數據前 10（自責分率 / 三振 / 勝投 / 救援 / WHIP）。'
                 '率定數（ERA、WHIP）已套官方規定局數門檻，榜上皆合格者。</div>'
                 + render_leader_cards(leaders.get("pitching", {}), mp.PITCHING_CATS))
    tabs = (
        '<div class="tabs">'
        '<input type="radio" name="bbtab" id="bbtab-div" checked>'
        '<input type="radio" name="bbtab" id="bbtab-bat">'
        '<input type="radio" name="bbtab" id="bbtab-pit">'
        '<div class="tablabels">'
        '<label for="bbtab-div">分區排名</label>'
        '<label for="bbtab-bat">打擊榜</label>'
        '<label for="bbtab-pit">投手榜</label>'
        '</div>'
        f'<div class="panel panel-div">{div_panel}</div>'
        f'<div class="panel panel-bat">{bat_panel}</div>'
        f'<div class="panel panel-pit">{pit_panel}</div>'
        '</div>'
    )
    asof_note = (
        '<p class="st-asof">資料來源：MLB 官方 StatsAPI（statsapi.mlb.com，與 MLB.com 一致）；'
        f'{season} 賽季例行賽，截至 {asof}。賽季進行中，排名與排行榜逐時更新，'
        '本頁為定期重生之資料頁，與最新狀態可能略有落差。'
        '本站為非官方資料整理站，無任何官方授權，球隊名稱與聯盟標誌權利屬各權利人所有。</p>'
    )
    body = (f'<h1 class="st-h1">MLB 排名 · 數據排行榜</h1>'
            f'<div class="st-sub">美國職棒大聯盟 {season} 賽季 · 六分區戰況 + 打擊／投手排行（截至 {asof}）。</div>'
            f'{tabs}{asof_note}')
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"MLB 排名與數據排行榜（{season}）", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = ba.graph_ld([ba.org_node(SITE), ba.website_node(SITE), coll,
                          ba.breadcrumb_node([("首頁", f"{BASE}/"), ("排名", canonical)])])
    desc = (f"MLB {season} 賽季例行賽六分區排名（截至 {asof}）、打擊排行（全壘打／打點／打擊率／盜壘）"
            f"與投手排行（自責分率／三振／勝投／救援）。資料來自官方 MLB StatsAPI。")
    return _shell(f"MLB 排名與數據排行榜（{season}）", desc, canonical, jsonld, body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--asof", default=datetime.date.today().isoformat(),
                    help="資料截點日（也用於 date-pinned standings 查詢，預設今天）")
    args = ap.parse_args()
    season, asof = args.season, args.asof

    leaders_path = ROOT / "leagues" / f"mlb-leaders-{season}.json"
    if not leaders_path.exists():
        raise SystemExit(f"❌ 缺 {leaders_path.relative_to(ROOT)}；先跑："
                         f" python3 scripts/fetch-mlb-players.py leaders --season {season}")
    leaders = json.loads(leaders_path.read_text(encoding="utf-8"))

    print(f"📡 MLB standings {season} @ {asof} (StatsAPI, date-pinned) …")
    recs = bf.team_records_asof(season, asof)
    ties = bf.div_tie_leaders(recs)
    print(f"   {len(recs)} 隊；{len(ties)} 分區並列首位")

    # snapshot for reproducibility / future cron diff
    snap = ROOT / "leagues" / f"mlb-standings-{season}.json"
    snap.write_text(json.dumps({"season": season, "asof": asof, "standings": recs},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   💾 {snap.relative_to(ROOT)}")

    out_dir = ROOT / "public-baseball" / "standings"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_page(recs, ties, leaders, season, asof), encoding="utf-8")
    print(f"✅ public-baseball/standings/index.html")

    # merge /standings/ into sitemap (keep landing + articles + teams; replace standings block)
    sm = ROOT / "public-baseball" / "sitemap.xml"
    keep = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
            if "/standings/" not in u] if sm.exists() else [f"{BASE}/"]
    urls = list(dict.fromkeys(keep + [f"{BASE}/standings/"]))
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                  f"{body}</urlset>\n", encoding="utf-8")
    print(f"🗺️  sitemap.xml → {len(urls)} URLs (+/standings/)")


if __name__ == "__main__":
    main()
