#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gen-cpbl-standings.py — 中職 CPBL 戰績 + 數據排行榜頁(public-baseball/cpbl/).

獨立於 MLB /standings/ 的 CPBL 專頁 /cpbl/，三個 server-rendered HTML 區塊
(CSS-only tabs，無 JS data fetch → crawler 看得到全部表格，對齊 HTML-over-PNG 房規)：
  · 戰績:中職單一聯盟 6 隊上半季戰績(排名/出賽/勝/敗/和/勝率/勝差/近況)
  · 打擊榜:打擊率 / 安打 / 全壘打 / 打點 / 盜壘 官方首頁 TOP5
  · 投手榜:防禦率 / 勝投 / 救援成功 / 中繼成功 / 奪三振 官方首頁 TOP5

⚠️ 資料性質與 MLB 不同：CPBL 沒有確認到穩定公開 JSON API，本頁吃的是
   leagues/cpbl-standings-leaders-<date>.json —— 一份從 cpbl.com.tw 官方首頁
   「人工擷取」的快照，「非自動更新」、且各項排行只有官方首頁公布的「前 5 名」(非完整榜)。
   頁面 as-of/警語必須誠實標注擷取日 + 非官方 + 非即時，避免手動靜態檔靜默過期。
   後續要更新：重抓官方首頁產新的 cpbl-standings-leaders-<date>.json，再跑本腳本。

版型沿用 build-articles 共用外殼 + baseball(navy/@BASEBALL)站身分，與 MLB 排名頁/球隊頁同系列。

用法:
  python3 scripts/gen-cpbl-standings.py [--snapshot leagues/cpbl-standings-leaders-2026-06-28.json]
  (不給 --snapshot 時自動取 leagues/cpbl-standings-leaders-*.json 中日期最新的一份)
⚠️ 跑序:build-articles.py 會整個覆寫 sitemap → 必須先 build-articles，再跑本腳本(各自 re-merge 自己的 path)。
"""
import argparse
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

SITE = ba.SITES.get("baseball")
BASE = SITE["base"]

# 官方首頁榜單呈現序(與 cpbl.com.tw 首頁一致)
BAT_ORDER = ["batting_average", "hits", "home_runs", "runs_batted_in", "stolen_bases"]
PIT_ORDER = ["era", "wins", "saves", "holds", "strikeouts"]

CPBL_CSS = """
.st-h1 { font-family: var(--font-display); font-size: clamp(30px,5vw,46px); line-height:1.1; margin: 4px 0 6px; }
.st-sub { color: var(--fg-soft); font-size: 15px; margin: 10px 0 22px; }
.st-sub b { color: var(--accent); }
/* CSS-only tabs: radios drive panel visibility, no JS */
.tabs > input[name="cptab"] { position:absolute; opacity:0; width:0; height:0; }
.tablabels { display:flex; flex-wrap:wrap; gap:8px; margin: 8px 0 22px; border-bottom:1px solid var(--line); }
.tablabels label { cursor:pointer; padding:9px 16px; font-size:14.5px; font-weight:700; color:var(--dim);
  border-bottom:2px solid transparent; margin-bottom:-1px; transition:color .15s, border-color .15s; }
.tablabels label:hover { color: var(--fg); }
.panel { display:none; }
#cptab-std:checked ~ .tablabels label[for="cptab-std"],
#cptab-bat:checked ~ .tablabels label[for="cptab-bat"],
#cptab-pit:checked ~ .tablabels label[for="cptab-pit"] { color: var(--accent); border-bottom-color: var(--accent); }
#cptab-std:checked ~ .panel-std,
#cptab-bat:checked ~ .panel-bat,
#cptab-pit:checked ~ .panel-pit { display:block; }
.std-table { width:100%; border-collapse:collapse; margin: 8px 0 14px; font-size: 14px; }
.std-table th, .std-table td { padding: 8px 6px; text-align:center; border-bottom:1px solid var(--line); white-space:nowrap; }
.std-table th { color: var(--dim); font-weight:600; font-size:12px; }
.std-table td.l, .std-table th.l { text-align:left; white-space:normal; }
.std-table td.rk { color:var(--dim); font-family:var(--font-mono); font-size:12.5px; }
.std-table tr.lead td.tm { font-weight:800; }
.std-pts { color: var(--accent); font-weight:800; }
.stk-pos { color:#5fb878; } .stk-neg { color:#d98a8a; }
.lb-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:8px 22px; margin: 10px 0 18px; }
.lb-card { border:1px solid var(--line); border-radius:12px; padding:12px 14px 8px; }
.lb-card h3 { font-size:14px; margin:0 0 6px; color:var(--fg); }
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
{CPBL_CSS}
</style>
</head>
<body>
{ba.theme_switch_html(SITE)}
<div class="container">{ba.site_header_html('cpbl', SITE)}
{body}
{ba.site_footer_html(SITE)}
</div>
<script>{ba.theme_switch_js(SITE)}</script>
</body>
</html>
"""


def _streak_span(stk):
    stk = (stk or "").strip()
    if not stk:
        return ""
    cls = "stk-pos" if stk.startswith("勝") else ("stk-neg" if stk.startswith("敗") else "")
    txt = html_lib.escape(stk)
    return f'<span class="{cls}">{txt}</span>' if cls else txt


def render_standings_table(standings, phase, asof):
    out = ['<div class="st-sub">中華職棒 CPBL '
           f'{html_lib.escape(phase)} 6 隊戰績，依官方戰績排名排序（截至 {asof}）。'
           '勝率、勝差採官方公布值；「和」為和局數。</div>']
    rows = ""
    for t in standings:
        lead = ' class="lead"' if t.get("rank") == 1 else ""
        gb = t.get("games_behind")
        gb_disp = "—" if gb in (None, "", "0") else html_lib.escape(str(gb))
        rows += (
            f'<tr{lead}>'
            f'<td class="rk">{t.get("rank","")}</td>'
            f'<td class="l tm">{html_lib.escape(t.get("team",""))}</td>'
            f'<td>{t.get("games","")}</td>'
            f'<td class="std-pts">{t.get("wins","")}</td>'
            f'<td>{t.get("losses","")}</td>'
            f'<td>{t.get("ties","")}</td>'
            f'<td>{html_lib.escape(str(t.get("winning_percentage","")))}</td>'
            f'<td>{gb_disp}</td>'
            f'<td>{_streak_span(t.get("streak",""))}</td>'
            '</tr>'
        )
    out.append(
        '<table class="std-table"><thead><tr>'
        '<th class="rk">#</th><th class="l">球隊</th><th>出賽</th><th>勝</th><th>敗</th>'
        '<th>和</th><th>勝率</th><th>勝差</th><th>近況</th>'
        f'</tr></thead><tbody>{rows}</tbody></table>'
    )
    return "\n".join(out)


def render_leader_cards(board, order):
    cards = []
    for c in order:
        cat = board.get(c)
        if not cat or not cat.get("rows"):
            continue
        trs = ""
        for r in cat["rows"]:
            trs += (f'<tr><td class="rk">{r.get("rank","")}</td>'
                    f'<td class="nm">{html_lib.escape(r.get("player",""))}</td>'
                    f'<td class="tm">{html_lib.escape(r.get("team",""))}</td>'
                    f'<td class="vl">{html_lib.escape(str(r.get("value","")))}</td></tr>')
        cards.append(
            f'<div class="lb-card"><h3>{html_lib.escape(cat.get("label_zh", c))}</h3>'
            f'<table><tbody>{trs}</tbody></table></div>'
        )
    return f'<div class="lb-grid">{"".join(cards)}</div>'


def build_page(snap):
    season = snap.get("season", 2026)
    phase = snap.get("season_phase", "")
    asof = snap.get("asof_taipei_date", "")
    fetched = snap.get("fetched_at_taipei", "")
    standings = snap.get("standings", [])
    leaders = snap.get("leaders", {})

    canonical = f"{BASE}/cpbl/"
    std_panel = render_standings_table(standings, phase, asof)
    bat_panel = ('<div class="st-sub">打擊數據官方首頁前 5 名（打擊率 / 安打 / 全壘打 / 打點 / 盜壘）。'
                 '此為官方首頁公布之 TOP5，非完整排行榜。</div>'
                 + render_leader_cards(leaders.get("batting", {}), BAT_ORDER))
    pit_panel = ('<div class="st-sub">投手數據官方首頁前 5 名（防禦率 / 勝投 / 救援成功 / 中繼成功 / 奪三振）。'
                 '此為官方首頁公布之 TOP5，非完整排行榜。</div>'
                 + render_leader_cards(leaders.get("pitching", {}), PIT_ORDER))
    tabs = (
        '<div class="tabs">'
        '<input type="radio" name="cptab" id="cptab-std" checked>'
        '<input type="radio" name="cptab" id="cptab-bat">'
        '<input type="radio" name="cptab" id="cptab-pit">'
        '<div class="tablabels">'
        '<label for="cptab-std">戰績</label>'
        '<label for="cptab-bat">打擊榜</label>'
        '<label for="cptab-pit">投手榜</label>'
        '</div>'
        f'<div class="panel panel-std">{std_panel}</div>'
        f'<div class="panel panel-bat">{bat_panel}</div>'
        f'<div class="panel panel-pit">{pit_panel}</div>'
        '</div>'
    )
    asof_note = (
        '<p class="st-asof">資料來源：中華職棒 CPBL 官方網站（cpbl.com.tw）首頁戰績與 TOP5 區塊，'
        f'於 {asof} 人工擷取之快照（擷取時間 {html_lib.escape(fetched)}）。'
        'CPBL 未提供穩定之公開即時 API，本頁為「非自動更新」之靜態快照；'
        '各項排行僅列官方首頁公布之「前 5 名」，非完整排行榜。'
        f'{season} 年{html_lib.escape(phase)}賽季進行中，戰績與排行隨賽事變動，本頁數據可能與最新狀態有落差。'
        '本站為非官方資料整理站，無任何官方授權；球隊名稱、聯盟標誌與相關權利屬中華職棒及各權利人所有。</p>'
    )
    body = (f'<h1 class="st-h1">中職 CPBL 戰績 · 數據排行</h1>'
            f'<div class="st-sub">中華職棒 {season} 年{html_lib.escape(phase)} · 6 隊戰績 + 打擊／投手 TOP5（截至 {asof}）。</div>'
            f'{tabs}{asof_note}')
    coll = {"@type": "CollectionPage", "@id": canonical, "url": canonical,
            "name": f"中職 CPBL 戰績與數據排行（{season} {phase}）", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{BASE}/#website"}}
    jsonld = ba.graph_ld([ba.org_node(SITE), ba.website_node(SITE), coll,
                          ba.breadcrumb_node([("首頁", f"{BASE}/"), ("中職", canonical)])])
    desc = (f"中華職棒 CPBL {season} 年{phase}戰績（截至 {asof}）：6 隊勝負勝率排名，"
            f"打擊排行（打擊率／安打／全壘打／打點／盜壘）與投手排行（防禦率／勝投／救援／中繼／奪三振）"
            f"官方首頁 TOP5。資料來自 cpbl.com.tw 官方首頁人工快照。")
    return _shell(f"中職 CPBL 戰績與數據排行（{season} {phase}）", desc, canonical, jsonld, body)


def _resolve_snapshot(arg):
    if arg:
        p = (ROOT / arg) if not pathlib.Path(arg).is_absolute() else pathlib.Path(arg)
        if not p.exists():
            raise SystemExit(f"❌ 找不到 snapshot：{arg}")
        return p
    cands = sorted(ROOT.glob("leagues/cpbl-standings-leaders-*.json"))
    if not cands:
        raise SystemExit("❌ leagues/ 下沒有 cpbl-standings-leaders-*.json；先抓官方首頁產 snapshot。")
    return cands[-1]  # 檔名含日期，字典序最後 = 最新


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=None,
                    help="CPBL 官方快照 JSON 路徑(預設取 leagues/cpbl-standings-leaders-*.json 最新)")
    args = ap.parse_args()

    snap_path = _resolve_snapshot(args.snapshot)
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    print(f"📄 CPBL snapshot: {snap_path.relative_to(ROOT)} "
          f"(asof {snap.get('asof_taipei_date')}, {len(snap.get('standings', []))} 隊)")

    out_dir = ROOT / "public-baseball" / "cpbl"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(build_page(snap), encoding="utf-8")
    print(f"✅ public-baseball/cpbl/index.html")

    # merge /cpbl/ into sitemap (keep landing/articles/teams/standings; replace cpbl block)
    sm = ROOT / "public-baseball" / "sitemap.xml"
    keep = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.read_text(encoding="utf-8"))
            if "/cpbl/" not in u] if sm.exists() else [f"{BASE}/"]
    urls = list(dict.fromkeys(keep + [f"{BASE}/cpbl/"]))
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    sm.write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                  f"{body}</urlset>\n", encoding="utf-8")
    print(f"🗺️  sitemap.xml → {len(urls)} URLs (+/cpbl/)")


if __name__ == "__main__":
    main()
