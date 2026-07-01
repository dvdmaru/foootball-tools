#!/usr/bin/env python3
"""戰況中心 build：/standings/index.html

單一 hub 頁，三個 tab：
  1. 賽程 · 積分  — 12 組 group block（積分榜 + 6 場賽程），SEO/GEO 友善 HTML
  2. 淘汰賽       — R32→決賽 bracket（6/27 小組賽結束後填真隊；目前 placeholder 對照表）
  3. 射手榜       — 金靴榜（6/11 開賽後由 fetch-results 填；目前 placeholder）

Data：public/fixtures-data.json（teams / matches / team_zh）+ fixtures/knockout.json
積分自動填的契約：當 matches[i] 帶 int 的 home_score / away_score 時即納入計算，
否則該場視為未開賽（[[feedback_pipeline_upstream_output_normalize]] 下游 contract）。

時間顯示一律 normalize，不 leak raw `03:00+1`（[[feedback_internal_token_leak_to_user_display]]）。
"""

import importlib.util
import json
import os
import pathlib
import unicodedata
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
FIXTURES = ROOT / "fixtures"

# 缺中文譯名的射手偵測：每次 render 收集，跑完寫檔 + 印出（launchd 下另推 LINE）。
# 房規＝每日只補當天實際進球者（不 seed 全部 1248 名球員）；此 list 讓 gap 永不無聲消失。
NOTIFY_PENDING = pathlib.Path(
    "/Users/charlie.chien/Library/CloudStorage/Dropbox/AI/CoWork/notify-system/pending"
)
MISSING_ZH_FILE = ROOT / "scripts" / "player-zh-missing.txt"
MISSING_ZH = []  # list of (player, team_code)，render_scorers 填、build() 收


def _norm_name(s):
    """去除變音符號 + casefold，讓 'Raúl Jiménez' 與 'Raul Jimenez' 都能對到中文譯名。"""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


def load_zh(filename):
    """讀 scripts/<filename>（curated 中文譯名 dict）→ normalized-key dict，用 _norm_name 對齊
    重音/大小寫。未收錄者顯示原文；新名出現時補一行即可（fetch 不碰這些檔，不會被覆寫）。
    player-zh.json = 射手中文譯名；team-zh.json = CPBL/MLB 隊名中文。"""
    p = ROOT / "scripts" / filename
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {_norm_name(k): v for k, v in raw.items() if not k.startswith("_")}


def load_player_zh():  # back-compat alias (importlib re-exports may reference it)
    return load_zh("player-zh.json")


PLAYER_ZH = load_zh("player-zh.json")
TEAM_ZH = load_zh("team-zh.json")

# ---- 沿用 build-articles 的共用 design tokens（單一來源，避免 drift）----
_spec = importlib.util.spec_from_file_location(
    "build_articles", ROOT / "scripts" / "build-articles.py"
)
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


def last_updated_taipei():
    """('2026-06-12 14:30', '2026-06-12') — 依資料檔 mtime（deterministic per content）。
    優先用 scorers.json/fixtures-data.json 較新的 mtime。"""
    cands = [PUBLIC / "fixtures-data.json", PUBLIC / "standings" / "scorers.json"]
    mtimes = [p.stat().st_mtime for p in cands if p.exists()]
    if not mtimes:
        return "", ""
    tp = datetime.utcfromtimestamp(max(mtimes)) + timedelta(hours=8)
    return tp.strftime("%Y-%m-%d %H:%M"), tp.strftime("%Y-%m-%d")


# ---------------- data ----------------

def load_data():
    fd = json.loads((PUBLIC / "fixtures-data.json").read_text(encoding="utf-8"))
    ko = json.loads((FIXTURES / "knockout.json").read_text(encoding="utf-8"))
    team_zh = fd["team_zh"]
    iso_by_code = {}
    for t in fd["teams"]:
        iso_by_code[t["code"]] = t["iso"]
    return fd["matches"], ko, team_zh, iso_by_code


def taipei_disp(match):
    """('6/12（五）03:00', '6/11 15:00 ET') — 不 leak raw +1 token"""
    raw = match["kickoff_taipei"]
    plus = 0
    if "+" in raw:
        raw, p = raw.split("+")
        plus = int(p)
    hh, mm = raw.split(":")
    et_base = datetime.strptime(match["date"], "%Y-%m-%d")
    tp = et_base + timedelta(days=plus)
    tp_str = f"{tp.month}/{tp.day}（{WK[tp.weekday()]}）{int(hh):02d}:{mm}"
    et_str = f"{et_base.month}/{et_base.day} {match['kickoff_et']} ET"
    return tp_str, et_str


def has_score(m):
    return isinstance(m.get("home_score"), int) and isinstance(m.get("away_score"), int)


def compute_standings(matches):
    """code -> dict(P,W,D,L,GF,GA,GD,Pts). 無比分的場次不計（未開賽=全 0）。"""
    tbl = {}

    def ensure(code):
        if code not in tbl:
            tbl[code] = {"P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0, "Pts": 0}
        return tbl[code]

    for m in matches:
        h, a = ensure(m["home_code"]), ensure(m["away_code"])
        if not has_score(m):
            continue
        hs, as_ = m["home_score"], m["away_score"]
        h["P"] += 1; a["P"] += 1
        h["GF"] += hs; h["GA"] += as_
        a["GF"] += as_; a["GA"] += hs
        if hs > as_:
            h["W"] += 1; h["Pts"] += 3; a["L"] += 1
        elif hs < as_:
            a["W"] += 1; a["Pts"] += 3; h["L"] += 1
        else:
            h["D"] += 1; a["D"] += 1; h["Pts"] += 1; a["Pts"] += 1
    for code, r in tbl.items():
        r["GD"] = r["GF"] - r["GA"]
    return tbl


# ---------------- render ----------------

def flag(iso):
    return f'<img class="std-flag" src="https://flagcdn.com/w160/{iso}.png" alt="" loading="lazy">'


def gd_str(gd):
    return f"+{gd}" if gd > 0 else str(gd)


def group_sort(codes, tbl):
    """組內排序：Pts → GD → GF → code（穩定）。"""
    return sorted(codes, key=lambda c: (-tbl[c]["Pts"], -tbl[c]["GD"], -tbl[c]["GF"], c))


def clinched_top2(code, group_codes, gmatches, tbl):
    """數學上鎖定前 2：列舉該組『剩餘賽程』所有結果（含追兵彼此對戰的零和），
    在對 code 最不利的情境下（code 剩餘全敗→停在現有積分）仍至多 1 隊積分 ≥ code，
    即保證至少第 2。會正確處理『兩追兵末輪互踢、不可能同時全勝』而不再高估威脅數。
    保守：積分相同(tiebreak 未定)一律當威脅；含 code 的剩餘比賽固定為 code 落敗(對手 +3)。"""
    from itertools import product
    floor = tbl[code]["Pts"]
    base = {c: tbl[c]["Pts"] for c in group_codes}
    remaining = [m for m in gmatches if not has_score(m)
                 and m["home_code"] in group_codes and m["away_code"] in group_codes]
    fixed = [m for m in remaining if code in (m["home_code"], m["away_code"])]
    enum_ms = [m for m in remaining if code not in (m["home_code"], m["away_code"])]
    worst = 0
    for combo in product(("H", "D", "A"), repeat=len(enum_ms)):
        pts = dict(base)
        for m in fixed:  # code 落敗 → 對手全取 3 分（對 code 最壞）
            opp = m["away_code"] if m["home_code"] == code else m["home_code"]
            pts[opp] += 3
        for m, r in zip(enum_ms, combo):
            h, a = m["home_code"], m["away_code"]
            if r == "H":
                pts[h] += 3
            elif r == "A":
                pts[a] += 3
            else:
                pts[h] += 1
                pts[a] += 1
        cnt = sum(1 for y in group_codes if y != code and pts[y] >= floor)
        if cnt > worst:
            worst = cnt
    return worst <= 1


def _worst_rivals_ge(code, group_codes, gmatches, tbl):
    """列舉該組剩餘賽程所有結果（code 剩餘固定落敗＝對 code 最壞），
    回傳『最壞情境下積分 ≥ code 現有積分的同組對手數』。worst≤1→鎖前2、worst≤2→鎖前3。"""
    from itertools import product
    floor = tbl[code]["Pts"]
    base = {c: tbl[c]["Pts"] for c in group_codes}
    remaining = [m for m in gmatches if not has_score(m)
                 and m["home_code"] in group_codes and m["away_code"] in group_codes]
    fixed = [m for m in remaining if code in (m["home_code"], m["away_code"])]
    enum_ms = [m for m in remaining if code not in (m["home_code"], m["away_code"])]
    worst = 0
    for combo in product(("H", "D", "A"), repeat=len(enum_ms)):
        pts = dict(base)
        for m in fixed:
            opp = m["away_code"] if m["home_code"] == code else m["home_code"]
            pts[opp] += 3
        for m, r in zip(enum_ms, combo):
            h, a = m["home_code"], m["away_code"]
            if r == "H":
                pts[h] += 3
            elif r == "A":
                pts[a] += 3
            else:
                pts[h] += 1
                pts[a] += 1
        cnt = sum(1 for y in group_codes if y != code and pts[y] >= floor)
        worst = max(worst, cnt)
    return worst


def _remaining_games(code, gmatches):
    return sum(1 for m in gmatches if not has_score(m)
               and code in (m["home_code"], m["away_code"]))


def _max_third_pts(gcodes, gmatches, tbl):
    """該組『第三名最終積分』的 sound 上界：整組踢完＝實際第三名積分；
    未踢完＝各隊 ceiling(現有+3×剩餘場)的第 3 高（第三名最終分必 ≤ 第 3 高 ceiling）。"""
    if all(has_score(m) for m in gmatches):
        return tbl[group_sort(gcodes, tbl)[2]]["Pts"]
    ceilings = sorted((tbl[c]["Pts"] + 3 * _remaining_games(c, gmatches)
                       for c in gcodes), reverse=True)
    return ceilings[2] if len(ceilings) >= 3 else (ceilings[-1] if ceilings else 0)


def clinched_qualification(code, own_g, groups, tbl):
    """數學鎖定晉級 32 強——即使在最壞情境下掉到小組第 3，也保證搶進 8 個最佳第三名：
      ① 保證至少小組第 3（最壞情境同組 ≥ 我積分者 ≤2）；
      ② 其餘 11 組中『第三名最終積分有可能 ≥ 我保底積分』的組數 ≤7
         → 至多 7 隊第三名能壓過我，我至差排第 8 名最佳第三名（8 取 8）仍晉級。
    上界皆取保守值（max third / 我用現有積分為保底），故只會漏報、不會錯報。"""
    gcodes = groups[own_g]["teams"]
    gmatches = groups[own_g]["matches"]
    if _worst_rivals_ge(code, gcodes, gmatches, tbl) > 2:   # 不保證前 3
        return False
    floor_pts = tbl[code]["Pts"]
    threats = sum(
        1 for g in groups if g != own_g
        and _max_third_pts(groups[g]["teams"], groups[g]["matches"], tbl) >= floor_pts
    )
    return threats <= 7


def compute_qualified(groups, tbl):
    """回傳 (adv_codes, lead_codes)：
    - adv_codes：掛實心『晉級』徽章 — 已鎖定前 2（in-progress 用 clinch、整組踢完用最終前 2），
      已鎖定最佳第三名（clinched_qualification：保證前 3＋保底分保證進最佳第三前 8），
      以及全 12 組踢完後算出的 8 個最佳第三名。
    - lead_codes：小組賽進行中『目前居晉級區』的當前前 2（未鎖定），只給淡色 highlight、不放字；
      未開賽(該組 0 場)的組不給，避免照種子序假標。"""
    adv, lead = set(), set()
    all_complete = all(
        all(has_score(m) for m in groups[g]["matches"]) for g in groups
    )
    for g in groups:
        gcodes = groups[g]["teams"]
        gmatches = groups[g]["matches"]
        complete = all(has_score(m) for m in gmatches)
        played = any(has_score(m) for m in gmatches)
        order = group_sort(gcodes, tbl)
        if complete:
            adv.update(order[:2])
        else:
            for c in gcodes:
                if clinched_top2(c, gcodes, gmatches, tbl):
                    adv.add(c)
            if played:
                for c in order[:2]:
                    if c not in adv:
                        lead.add(c)
        # 最佳第三名 clinch 對「所有組」一致成立（含已完賽組的第 3 名）。
        # 原本只在未完賽分支呼叫 clinched_qualification，導致不對稱：
        # 未完賽組第三（如 ENG/GHA）被標、已完賽組同為保底分第三（如 ECU/SWE/PAR/BIH）
        # 卻漏標。clinched_qualification 已含「保證前 3」與保底分上界檢查，sound、只漏不錯。
        for c in gcodes:
            if c not in adv and clinched_qualification(c, g, groups, tbl):
                adv.add(c)
    # 8 個最佳第三名：全部小組踢完才算得出
    if all_complete and groups:
        thirds = [group_sort(groups[g]["teams"], tbl)[2] for g in groups
                  if len(groups[g]["teams"]) >= 3]
        for c in group_sort(thirds, tbl)[:8]:
            adv.add(c)
    return adv, lead


def render_group_block(grp, teams, matches, tbl, adv_codes, lead_codes):
    """teams: list of code（該組 4 隊）"""
    rows = group_sort(teams, tbl)
    body = []
    for i, code in enumerate(rows):
        r = tbl[code]
        rank = i + 1
        cls = ""
        badge = ""
        if code in adv_codes:
            cls = " std-adv"  # 已鎖定晉級（含最佳第三）
            badge = '<span class="std-q std-q-direct">晉級</span>'
        elif code in lead_codes:
            cls = " std-third"  # 目前居晉級區（未鎖定）— 淡色，不放字
        body.append(
            f'<tr class="{cls.strip()}">'
            f'<td class="std-rank">{rank}</td>'
            f'<td class="std-team">{flag(ISO[code])}<span class="std-name">{ZH.get(code, code)}</span>{badge}</td>'
            f'<td>{r["P"]}</td><td>{r["W"]}</td><td>{r["D"]}</td><td>{r["L"]}</td>'
            f'<td>{r["GF"]}</td><td>{r["GA"]}</td><td class="std-gd">{gd_str(r["GD"])}</td>'
            f'<td class="std-pts">{r["Pts"]}</td>'
            f"</tr>"
        )
    standings_table = (
        '<table class="std-table"><thead><tr>'
        '<th class="std-rank">#</th><th class="std-team-h">球隊</th>'
        '<th title="出賽">賽</th><th title="勝">勝</th><th title="和">和</th><th title="負">負</th>'
        '<th title="進球">進</th><th title="失球">失</th><th title="淨勝球">差</th>'
        '<th class="std-pts" title="積分">分</th>'
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )

    # 賽程列
    ml = []
    for m in matches:
        tp, et = taipei_disp(m)
        if has_score(m):
            score = f'<span class="std-score">{m["home_score"]}<span class="std-dash">-</span>{m["away_score"]}</span>'
        else:
            score = '<span class="std-vs">vs</span>'
        ml.append(
            '<li class="std-match">'
            f'<div class="std-when"><span class="std-tp">{tp}</span><span class="std-et">{et}</span></div>'
            '<div class="std-fixture">'
            f'<span class="std-side std-home">{ZH.get(m["home_code"], m["home_team"])}{flag(m["home_iso"])}</span>'
            f"{score}"
            f'<span class="std-side std-away">{flag(m["away_iso"])}{ZH.get(m["away_code"], m["away_team"])}</span>'
            "</div>"
            f'<div class="std-venue">{m["city"]} · {m["stadium"]}</div>'
            "</li>"
        )
    match_list = '<ul class="std-matches">' + "".join(ml) + "</ul>"

    return (
        f'<section class="std-group" id="group-{grp}">'
        f'<h3 class="std-group-h"><span class="std-group-tag">Group</span>{grp}</h3>'
        f"{standings_table}{match_list}"
        "</section>"
    )


def render_league_table(rows, logos=None):
    """Single standings table for a round-robin / per-conference league. `rows`: the
    normalized standings dicts from leagues/<comp>.json (rank/team_name/played/win/draw/
    lose/gf/ga/gd/points/team_code). Source-agnostic — reuses the WC std-table markup,
    no groups, no bracket. `logos`: optional team_code -> club-logo url (leagues use club
    crests, not country flags). Used by the league standings path; WC path is untouched."""
    logos = logos or {}
    body = []
    for r in rows:
        code = str(r.get("team_code", ""))
        logo = logos.get(code)
        crest = f'<img class="std-flag" src="{logo}" alt="" loading="lazy">' if logo else ""
        body.append(
            "<tr>"
            f'<td class="std-rank">{r.get("rank", "")}</td>'
            f'<td class="std-team">{crest}<span class="std-name">{r.get("team_name", "")}</span></td>'
            f'<td>{r.get("played", 0)}</td><td>{r.get("win", 0)}</td>'
            f'<td>{r.get("draw", 0)}</td><td>{r.get("lose", 0)}</td>'
            f'<td>{r.get("gf", 0)}</td><td>{r.get("ga", 0)}</td>'
            f'<td class="std-gd">{gd_str(r.get("gd", 0))}</td>'
            f'<td class="std-pts">{r.get("points", 0)}</td>'
            "</tr>"
        )
    return (
        '<table class="std-table"><thead><tr>'
        '<th class="std-rank">#</th><th class="std-team-h">球隊</th>'
        '<th title="出賽">賽</th><th title="勝">勝</th><th title="和">和</th><th title="負">負</th>'
        '<th title="進球">進</th><th title="失球">失</th><th title="淨勝球">差</th>'
        '<th class="std-pts" title="積分">分</th>'
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )


def render_baseball_table(rows, logos=None):
    """Single standings table for a baseball league (CPBL/MLB). `rows`: normalized standings
    from leagues/<comp>.json (rank/team_name/win/lose/pct/games_behind/group/team_code).
    Baseball columns: #/球隊/勝/負/勝率/勝差 — no draw, no run-difference, no points (reuses the
    std-table markup). Team names localized via team-zh.json (TEAM_ZH, _norm_name fuzzy). A
    split-season (CPBL 上/下半季) renders one sub-table per group. WC/soccer paths untouched."""
    logos = logos or {}
    groups, seen = [], {}
    for r in rows:
        g = r.get("group", "") or ""
        if g not in seen:
            seen[g] = []
            groups.append(g)
        seen[g].append(r)

    def _one(grp_rows):
        body = []
        for r in grp_rows:
            code = str(r.get("team_code", ""))
            logo = logos.get(code)
            crest = f'<img class="std-flag" src="{logo}" alt="" loading="lazy">' if logo else ""
            name = TEAM_ZH.get(_norm_name(r.get("team_name", "")), r.get("team_name", ""))
            gb = r.get("games_behind", 0) or 0
            gb_disp = "—" if gb <= 0 else f"{gb:g}"
            body.append(
                "<tr>"
                f'<td class="std-rank">{r.get("rank", "")}</td>'
                f'<td class="std-team">{crest}<span class="std-name">{name}</span></td>'
                f'<td>{r.get("win", 0)}</td><td>{r.get("lose", 0)}</td>'
                f'<td>{r.get("pct", "")}</td>'
                f'<td class="std-gd">{gb_disp}</td>'
                "</tr>"
            )
        return (
            '<table class="std-table"><thead><tr>'
            '<th class="std-rank">#</th><th class="std-team-h">球隊</th>'
            '<th title="勝">勝</th><th title="負">負</th>'
            '<th title="勝率">勝率</th><th title="勝差">勝差</th>'
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        )

    if len(groups) <= 1:
        return _one(rows)
    out = []
    for g in groups:
        out.append(
            '<section class="std-group">'
            f'<h3 class="std-group-h"><span class="std-group-tag">分區</span>{g or "戰績"}</h3>'
            f"{_one(seen[g])}</section>"
        )
    return "".join(out)


def zh_placeholder(name):
    """英文 placeholder 隊名 → 中文（避免 raw upstream token leak 到 user-facing）。
    開賽填真隊後（中文名）原樣回傳。"""
    import re
    m = re.match(r"Winner Group ([A-L])$", name)
    if m:
        return f"{m.group(1)} 組第一"
    m = re.match(r"Runner-up Group ([A-L])$", name)
    if m:
        return f"{m.group(1)} 組第二"
    m = re.match(r"Winner Match (\d+)$", name)
    if m:
        return f"第 {m.group(1)} 場勝者"
    m = re.match(r"Loser Match (\d+)$", name)
    if m:
        return f"第 {m.group(1)} 場敗者"
    m = re.match(r"Best 3rd \(Groups ([A-L/]+)\)$", name)
    if m:
        return f"最佳第三名（{m.group(1)} 組）"
    return name


def render_bracket(ko):
    """淘汰賽對照表 — 已確定的對位填真隊（帶國旗），其餘待小組收官。"""
    zh2iso = {ZH[c]: ISO[c] for c in ZH if c in ISO}

    import re as _re
    by_num = {m["match_number"]: m for m in ko if "match_number" in m}
    resolved = {m["match_number"]: {"home": m["home_team"], "away": m["away_team"]}
                for m in ko if "match_number" in m}

    def _winner(mn):
        m = by_num.get(mn)
        if not m or not has_score(m):
            return None
        if m.get("winner"):
            return m["winner"]
        if m["home_score"] > m["away_score"]:
            return resolved[mn]["home"]
        if m["away_score"] > m["home_score"]:
            return resolved[mn]["away"]
        return None  # 平手待 PK：請在該場填 winner 欄

    _chg = True
    while _chg:
        _chg = False
        for _mn, _r in resolved.items():
            for _side in ("home", "away"):
                _mm = _re.match(r"Winner Match (\d+)$", _r[_side])
                if _mm:
                    _w = _winner(int(_mm.group(1)))
                    if _w and _w != _r[_side]:
                        _r[_side] = _w
                        _chg = True

    def ko_team(name, side):
        iso = zh2iso.get(name)
        fl = flag(iso) if iso else ""
        return (f'<span class="std-ko-team std-ko-{side}">'
                f'{fl}<span class="std-ko-name">{zh_placeholder(name)}</span></span>')

    round_label = {
        "R32": "32 強", "R16": "16 強", "QF": "8 強",
        "SF": "4 強", "3rd": "季軍戰", "Final": "決賽",
    }
    order = ["R32", "R16", "QF", "SF", "3rd", "Final"]
    by_round = {}
    for m in ko:
        by_round.setdefault(m["round"], []).append(m)
    blocks = []
    for rnd in order:
        ms = by_round.get(rnd, [])
        if not ms:
            continue
        rows = []
        for m in ms:
            tp = datetime.strptime(m["date"], "%Y-%m-%d")
            when = f"{tp.month}/{tp.day}（{WK[tp.weekday()]}）"
            _r = resolved.get(m.get("match_number"),
                              {"home": m["home_team"], "away": m["away_team"]})
            if has_score(m):
                mid = (f'<span class="std-ko-score">{m["home_score"]}'
                       f'<span class="std-dash">-</span>{m["away_score"]}</span>')
            else:
                mid = '<span class="std-vs">vs</span>'
            rows.append(
                '<li class="std-ko-row">'
                f'<span class="std-ko-when">{when}</span>'
                f'{ko_team(_r["home"], "home")}'
                f'{mid}'
                f'{ko_team(_r["away"], "away")}'
                f'<span class="std-ko-venue">{m.get("city","")}</span>'
                "</li>"
            )
        blocks.append(
            f'<section class="std-ko-round"><h3 class="std-group-h">'
            f'<span class="std-group-tag">Round</span>{round_label.get(rnd, rnd)}</h3>'
            f'<ul class="std-ko-list">{"".join(rows)}</ul></section>'
        )
    return "".join(blocks)


def render_scorers(scorers, updated):
    """射手榜 table（#4）。scorers: list of dict(rank/player/team_code/goals/assists)。"""
    if not scorers:
        return ('<div class="std-banner">👟 金靴榜／助攻榜將在 <b>6/11</b> 開賽後每日更新。'
                '小組賽期間每場進球都會累積到這裡。</div>'
                '<div class="std-stats-empty">⚽<br>開賽後見真章</div>')
    rows = []
    MISSING_ZH.clear()
    for s in scorers:
        code = (s.get("team_code") or "").lower()
        flag_img = (f'<img class="std-flag" src="https://flagcdn.com/w160/{ISO.get(s["team_code"], code)}.png" alt="" loading="lazy">'
                    if s.get("team_code") else "")
        team_zh = ZH.get(s.get("team_code"), s.get("team_code", ""))
        assists = s.get("assists")
        a_cell = str(assists) if isinstance(assists, int) else "—"
        zh = PLAYER_ZH.get(_norm_name(s["player"]))
        if not zh:
            MISSING_ZH.append((s["player"], s.get("team_code") or ""))
        scorer_cell = (f'<span class="sc-en">{s["player"]}</span><span class="sc-zh">{zh}</span>'
                       if zh else s["player"])
        rows.append(
            '<tr>'
            f'<td class="std-rank">{s.get("rank","")}</td>'
            f'<td class="std-scorer">{scorer_cell}</td>'
            f'<td class="std-scorer-team">{flag_img}<span>{team_zh}</span></td>'
            f'<td class="std-pts">{s["goals"]}</td>'
            f'<td>{a_cell}</td>'
            '</tr>'
        )
    note = (f'<div class="std-banner std-live">👟 金靴榜更新於 <b>{updated}</b> · 小組賽每場進球即時累積</div>'
            if updated else '')
    return (note + '<table class="std-table std-scorers-table"><thead><tr>'
            '<th class="std-rank">#</th><th class="std-team-h">球員</th><th class="std-team-h">球隊</th>'
            '<th class="std-pts" title="進球">球</th><th title="助攻">助</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>')


def render_page(matches, ko, played_any, scorers=None, scorers_updated=None):
    tbl = compute_standings(matches)
    # group → 4 teams（保持 fixture 出現序去重）
    groups = {}
    for m in matches:
        g = m["group"]
        groups.setdefault(g, {"teams": [], "matches": []})
        for c in (m["home_code"], m["away_code"]):
            if c not in groups[g]["teams"]:
                groups[g]["teams"].append(c)
        groups[g]["matches"].append(m)

    adv_codes, lead_codes = compute_qualified(groups, tbl)
    group_blocks = "".join(
        render_group_block(g, groups[g]["teams"], groups[g]["matches"], tbl, adv_codes, lead_codes)
        for g in sorted(groups)
    )

    if played_any:
        banner = ('<div class="std-banner std-live">🔴 小組賽進行中 · 積分與比分每日自動更新'
                  '（每組前 2 名 <b>晉級</b>，8 個最佳第三名亦晉級 32 強）</div>')
    else:
        banner = ('<div class="std-banner">⚽ 小組賽 <b>6/11</b> 開踢 · 比分與積分將在開賽後每日自動更新。'
                  '下方為完整 72 場賽程（台北時間）。</div>')

    bracket_html = render_bracket(ko)
    bracket_note = ('<div class="std-banner">🏆 淘汰賽 <b>6/28</b> 開打（48 隊制：32 強 → 16 強 → 8 強 → 4 強 → 決賽）。'
                    '對戰組合將在 6/27 小組賽全部結束後填入真實球隊，目前顯示賽程框架。</div>')
    stats_note = render_scorers(scorers, scorers_updated)

    title = "戰況中心"
    desc = "2026 世界盃完整賽程、12 組積分榜、淘汰賽對照表與射手榜 — 台北時間，每日自動更新。"
    og_img = f"{SITE}/og-home.png"
    url = f"{SITE}/standings/"

    updated_disp, updated_iso = last_updated_taipei()
    updated_line = f"最後更新：{updated_disp} 台北時間 · " if updated_disp else ""
    webpage_ld = {
        "@type": "WebPage",
        "@id": url,
        "url": url,
        "name": f"{title}｜2026 世界盃",
        "description": desc,
        "inLanguage": "zh-Hant",
        "isPartOf": {"@id": f"{SITE}/#website"},
        "about": {"@id": f"{SITE}/#worldcup2026"},
    }
    if updated_iso:
        webpage_ld["dateModified"] = updated_iso
    crumb = breadcrumb_node([("首頁", f"{SITE}/"), ("戰況中心", url)])
    jsonld = graph_ld([org_node(), website_node(), tournament_node(), webpage_ld, crumb])

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}｜2026 世界盃 賽程・積分・淘汰賽・射手榜 @FOOOTBALL</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{url}">
{jsonld}
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{title}｜2026 世界盃 賽程・積分・射手榜">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{og_img}">
<meta property="og:site_name" content="@FOOOTBALL">
<meta property="og:locale" content="zh_TW">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}｜2026 世界盃 賽程・積分・射手榜">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{og_img}">
{GA_SNIPPET}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;900&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{PAGE_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">
{site_header_html('standings')}
  <div class="std-hero">
    <div class="std-kicker">LIVE · 2026 WORLD CUP</div>
    <h1 class="std-title">戰況中心</h1>
    <p class="std-sub">完整賽程 · 12 組積分榜 · 淘汰賽對照 · 射手榜 — 台北時間，開賽後每日自動更新</p>
  </div>

  <div class="std-tabs" role="tablist">
    <button class="std-tab active" data-tab="groups" role="tab">賽程 · 積分</button>
    <button class="std-tab" data-tab="bracket" role="tab">淘汰賽</button>
    <button class="std-tab" data-tab="stats" role="tab">射手榜</button>
  </div>

  <div class="std-panel active" id="panel-groups">
    {banner}
    <div class="std-groups-grid">{group_blocks}</div>
    <div class="std-rules" style="margin:30px auto 4px;max-width:760px;padding:16px 18px;border:1px solid rgba(212,175,55,.32);border-radius:10px;background:rgba(212,175,55,.06);font-size:14.5px;line-height:1.9;text-align:center">
      <strong style="color:#d4af37;letter-spacing:1px">規則速查</strong>　看不懂積分排序或晉級門檻？
      <a href="/articles/world-cup-points-tiebreakers/" style="color:#0d2818;font-weight:700">積分與晉級規則</a> ·
      <a href="/articles/world-cup-2026-format/" style="color:#0d2818;font-weight:700">賽制全解</a> ·
      <a href="/articles/knockout-extra-time-penalties/" style="color:#0d2818;font-weight:700">延長賽與點球</a>
    </div>
  </div>

  <div class="std-panel" id="panel-bracket">
    {bracket_note}
    <div class="std-ko-grid">{bracket_html}</div>
  </div>

  <div class="std-panel" id="panel-stats">
    {stats_note}
  </div>

  <footer class="std-footer">
    <div class="std-foot-cta">👉 訂閱你的球隊賽程，自動同步到行事曆：<a href="/">foootball.twtools.cc</a></div>
    <div class="std-foot-links">
      <a href="/">賽程訂閱</a> · <a href="/articles/">每日戰報</a> · <a href="https://medium.com/@foootball" target="_blank" rel="noopener">Medium ↗</a>
    </div>
    <div class="std-foot-fine">{updated_line}賽程／比分資料每日更新 · 時間為台北時間（北美場次標註當地 ET）</div>
    {DISCLAIMER_HTML}
  </footer>
</div>
<script>
{THEME_SWITCH_JS}
(function() {{
  const tabs = document.querySelectorAll('.std-tab');
  const panels = document.querySelectorAll('.std-panel');
  function show(name) {{
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === name));
    panels.forEach(p => p.classList.toggle('active', p.id === 'panel-' + name));
    try {{ history.replaceState(null, '', '#' + name); }} catch (e) {{}}
  }}
  tabs.forEach(t => t.addEventListener('click', () => show(t.dataset.tab)));
  const h = (location.hash || '').replace('#', '');
  if (['groups','bracket','stats'].includes(h)) show(h);
}})();
</script>
</body>
</html>
"""


PAGE_CSS = """
.container { max-width: 980px; margin: 0 auto; position: relative; z-index: 1; }
.std-hero { margin-bottom: 26px; }
.std-kicker { font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px; text-transform: uppercase; color: var(--accent); font-weight: 600; margin-bottom: 12px; display: inline-flex; align-items: center; gap: 9px; }
.std-kicker::before { content: ''; width: 22px; height: 2px; background: var(--accent); }
.std-title { font-family: var(--font-display); font-weight: 400; font-size: clamp(34px, 6vw, 52px); line-height: 1.08; color: var(--fg); letter-spacing: 0.5px; margin-bottom: 12px; }
.std-sub { font-size: 15.5px; color: var(--fg-soft); line-height: 1.6; max-width: 640px; }

.std-tabs { display: flex; gap: 8px; margin: 28px 0 24px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.std-tab { font-family: var(--font-ui); font-size: 14px; font-weight: 700; color: var(--dim); background: none; border: none; cursor: pointer; padding: 11px 16px; border-bottom: 2.5px solid transparent; margin-bottom: -1px; transition: color .15s, border-color .15s; letter-spacing: .5px; }
.std-tab:hover { color: var(--fg); }
.std-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.std-panel { display: none; }
.std-panel.active { display: block; animation: stdfade .25s ease; }
@keyframes stdfade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

.std-banner { background: var(--accent-soft); border: 1px solid var(--accent-line); border-radius: var(--radius-sm); padding: 13px 18px; font-size: 14px; color: var(--fg-soft); line-height: 1.6; margin-bottom: 26px; }
.std-banner b { color: var(--accent); font-weight: 800; }
.std-banner.std-live { background: color-mix(in srgb, #e0392b 12%, transparent); border-color: color-mix(in srgb, #e0392b 40%, transparent); }

.std-groups-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; }
@media (max-width: 760px) { .std-groups-grid { grid-template-columns: 1fr; } }

.std-group { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px 18px 8px; box-shadow: 0 4px 16px var(--sheet-shadow); }
.std-group-h { font-family: var(--font-display); font-weight: 400; font-size: 26px; color: var(--fg); letter-spacing: 1px; display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.std-group-tag { font-family: var(--font-mono); font-size: 10px; letter-spacing: 2px; color: var(--dim); text-transform: uppercase; font-weight: 600; }

.std-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 16px; }
.std-table th { font-family: var(--font-mono); font-weight: 600; font-size: 10.5px; letter-spacing: .5px; color: var(--dim); text-transform: uppercase; padding: 6px 5px; text-align: center; border-bottom: 1.5px solid var(--line-2); }
.std-table th.std-team-h { text-align: left; padding-left: 4px; }
.std-table td { padding: 7px 5px; text-align: center; color: var(--fg-soft); border-bottom: 1px solid var(--line); }
.std-table tr:last-child td { border-bottom: none; }
.std-rank { width: 22px; color: var(--faint); font-family: var(--font-mono); font-size: 12px; }
.std-team { text-align: left !important; display: flex; align-items: center; gap: 8px; }
.std-name { color: var(--fg); font-weight: 600; }
.std-flag { width: 22px; height: 15px; object-fit: cover; border-radius: 2px; box-shadow: 0 0 0 1px var(--line-2); flex-shrink: 0; }
.std-gd { font-variant-numeric: tabular-nums; }
.std-pts { color: var(--fg) !important; font-weight: 800; font-variant-numeric: tabular-nums; }
.std-adv .std-name { color: var(--accent); }
.std-adv td { background: var(--accent-soft); }
.std-third td { background: color-mix(in srgb, var(--accent-soft) 50%, transparent); }
.std-q { font-size: 9px; font-family: var(--font-mono); letter-spacing: .5px; padding: 1px 5px; border-radius: 99px; margin-left: 2px; }
.std-q-direct { background: var(--accent); color: var(--accent-ink); }
.std-q-maybe { background: var(--surface-3); color: var(--dim); }

.std-matches { list-style: none; padding: 0; margin: 0; border-top: 1px dashed var(--line-2); }
.std-match { padding: 9px 2px; border-bottom: 1px solid var(--line); display: grid; grid-template-columns: 1fr; gap: 4px; }
.std-match:last-child { border-bottom: none; }
.std-when { display: flex; align-items: baseline; gap: 8px; }
.std-tp { font-size: 12.5px; color: var(--fg); font-weight: 600; }
.std-et { font-family: var(--font-mono); font-size: 10px; color: var(--faint); }
.std-fixture { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
.std-side { display: flex; align-items: center; gap: 7px; font-size: 13.5px; color: var(--fg); font-weight: 500; }
.std-home { justify-content: flex-end; text-align: right; }
.std-away { justify-content: flex-start; text-align: left; }
.std-vs { font-family: var(--font-mono); font-size: 10px; color: var(--faint); letter-spacing: 1px; }
.std-score { font-family: var(--font-display); font-size: 17px; color: var(--fg); letter-spacing: 1px; }
.std-ko-score { font-family: var(--font-display); font-weight: 700; font-size: 15px; color: var(--fg); letter-spacing: 1px; white-space: nowrap; }
.std-dash { color: var(--faint); margin: 0 2px; }
.std-venue { font-size: 11px; color: var(--dim); text-align: center; }

.std-ko-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 20px; }
@media (max-width: 760px) { .std-ko-grid { grid-template-columns: 1fr; } }
.std-ko-round { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: 18px; box-shadow: 0 4px 16px var(--sheet-shadow); }
.std-ko-list { list-style: none; padding: 0; margin: 0; }
.std-ko-row { display: grid; grid-template-columns: auto 1fr auto 1fr; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
.std-ko-row:last-child { border-bottom: none; }
.std-ko-when { font-family: var(--font-mono); font-size: 10.5px; color: var(--dim); }
.std-ko-team { color: var(--fg-soft); display: flex; align-items: center; gap: 6px; min-width: 0; }
.std-ko-home { justify-content: flex-end; text-align: right; }
.std-ko-team .std-flag { margin: 0; }
.std-ko-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.std-ko-venue { display: none; }

.std-stats-empty { text-align: center; color: var(--faint); font-size: 18px; line-height: 2; padding: 60px 0; font-family: var(--font-display); letter-spacing: 2px; }
.std-scorers-table { max-width: 560px; }
.std-scorers-table td { padding: 10px 8px; }
.std-scorer { text-align: left !important; color: var(--fg); font-weight: 700; }
.std-scorer .sc-en { display: block; }
.std-scorer .sc-zh { display: block; font-size: .82em; font-weight: 500; color: var(--fg-soft); margin-top: 1px; letter-spacing: .3px; }
.std-scorer-team { text-align: left !important; }
.std-scorer-team span { color: var(--fg-soft); }
.std-scorer-team .std-flag { display: inline-block; vertical-align: middle; margin-right: 7px; }

.std-footer { margin-top: 56px; padding-top: 26px; border-top: 1px solid var(--line); text-align: center; }
.std-foot-cta { font-size: 15px; color: var(--fg); margin-bottom: 12px; font-weight: 600; }
.std-foot-cta a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-line); }
.std-foot-links { font-family: var(--font-mono); font-size: 12px; letter-spacing: 1px; color: var(--dim); margin-bottom: 10px; }
.std-foot-links a { color: var(--dim); text-decoration: none; }
.std-foot-links a:hover { color: var(--accent); }
.std-foot-fine { font-size: 11px; color: var(--faint); line-height: 1.6; }
"""


def load_scorers():
    p = PUBLIC / "standings" / "scorers.json"
    if not p.exists():
        return [], None
    d = json.loads(p.read_text(encoding="utf-8"))
    return d.get("scorers", []), d.get("updated")


def _notify_line(msg):
    """寫 .txt 到 notify-system/pending/ 觸發 LINE 推播（複用 Daily 通知管線）。"""
    if not NOTIFY_PENDING.exists():
        print("⚠️ notify-system pending/ 不存在，跳過 LINE 通知")
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = NOTIFY_PENDING / f"foootball-standings-missingzh-{ts}.txt"
    out.write_text(msg, encoding="utf-8")
    print(f"📲 缺譯名通知 queued → {out.name}")


def report_missing_zh():
    """射手榜有查無中文譯名的射手 → 寫 player-zh-missing.txt + 印出；
    launchd 下（STANDINGS_NOTIFY=1）另推 LINE，提醒當天補名。無缺則清掉舊檔。"""
    if not MISSING_ZH:
        if MISSING_ZH_FILE.exists():
            MISSING_ZH_FILE.unlink()
        return
    lines = [f'{p}\t{c}' for p, c in MISSING_ZH]
    body = ("# 射手榜查無中文譯名（房規：維基全名優先，缺退台媒姓氏）\n"
            "# 補進 scripts/player-zh.json 後重跑 build-standings.py 即消失\n"
            + "\n".join(lines) + "\n")
    MISSING_ZH_FILE.write_text(body, encoding="utf-8")
    names = "、".join(p for p, _ in MISSING_ZH)
    print(f"⚠️ {len(MISSING_ZH)} 個射手缺中文譯名（站上暫顯英文）：{names}")
    print(f"   清單 → {MISSING_ZH_FILE}")
    if os.environ.get("STANDINGS_NOTIFY") == "1":
        msg = (f"👟 戰況中心射手榜：{len(MISSING_ZH)} 個新射手缺中文譯名\n"
               f"{names}\n（站上暫顯英文，補 player-zh.json 即可）")
        _notify_line(msg)


def build():
    global ZH, ISO
    matches, ko, ZH, ISO = load_data()
    played_any = any(has_score(m) for m in matches)
    scorers, scorers_updated = load_scorers()
    html = render_page(matches, ko, played_any, scorers, scorers_updated)
    out = PUBLIC / "standings"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    report_missing_zh()
    state = "進行中（有比分）" if played_any else "未開賽（賽程 only）"
    print(f"✅ /standings/index.html — {len(matches)} 場賽程 / 12 組 / 射手榜 {len(scorers)} 人 / 狀態：{state}")


if __name__ == "__main__":
    build()
