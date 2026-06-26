#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build-facts.py — typed, rule-enriched facts packs for baseball deep articles.

Why this exists (2026-06-26 retro): tonight's cross-check P0s were NOT writing errors —
they were *facts/rule* errors that the Sonnet writer faithfully transcribed because the
facts pack had GAPS the writer then filled with (wrong) domain knowledge:
  - 跨聯盟 vs 跨分區: facts lacked the league/division relationship → writer inferred wrong.
  - ERA「全聯盟第二」: facts lacked the qualified-innings rule → writer ranked an unqualified
    pitcher into a leaderboard.
  - 白襪「獨居第一」: facts lacked the same-pct tie relationship.

Fix: compute the RULES at the data layer and emit them as facts. Then "禁 free-recall" stops
being a hope and becomes structural — the writer can only state what's in the (now complete) pack.

Data source = official MLB StatsAPI (via fetch-mlb-players.call). All numbers authoritative.

Usage:
  python3 scripts/build-facts.py standings-roundup --date 2026-06-25 [--season 2026]
  python3 scripts/build-facts.py game-recap --pk 778123 [--season 2026]
  python3 scripts/build-facts.py matchup --home "San Diego Padres" --away "Atlanta Braves"
  python3 scripts/build-facts.py player-qual --pid 660271 --team LAD --date 2026-06-25
Output → facts/<type>-<key>.json (and prints a human summary).
"""
import argparse
import datetime
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


mp = _load("fetch_mlb_players", "fetch-mlb-players.py")
bs = _load("build_standings", "build-standings.py")

FACTS_DIR = ROOT / "facts"
LEAGUE_ZH = {103: "美聯", 104: "國聯"}
LEAGUE_EN = {103: "American League", 104: "National League"}


def _zh(name):
    return bs.TEAM_ZH.get(bs._norm_name(name), name)


def team_records_asof(season, date=None):
    """StatsAPI standings as of a date (official; independent of computed-from-games).
    date=YYYY-MM-DD returns standings *after that day's games*. None = current.
    /standings returns SHORT team names ("Braves") → join /teams for full name + abbr so
    zh mapping and name/abbr matching work."""
    tmap = {t["id"]: t for t in mp.teams(season)}
    out = []
    ds = f"&date={date}" if date else ""
    for league_id in (103, 104):
        d = mp.call(f"/standings?leagueId={league_id}&season={season}"
                    f"&standingsTypes=regularSeason{ds}")
        for rec in d.get("records", []):
            div = rec.get("division", {}).get("id")
            for t in rec.get("teamRecords", []):
                sp = {s["type"]: s for s in t.get("records", {}).get("splitRecords", [])}
                home, away = sp.get("home", {}), sp.get("away", {})
                tid = t["team"]["id"]
                ti = tmap.get(tid, {})
                full = ti.get("name") or t["team"]["name"]
                out.append({
                    "team_id": tid, "name": full,
                    "name_short": t["team"]["name"], "abbr": ti.get("abbr", ""),
                    "name_zh": _zh(full),
                    "league_id": league_id, "division_id": div,
                    "division_zh": mp.DIV_ZH.get(div, ""),
                    "wins": t["wins"], "losses": t["losses"],
                    "pct": t.get("winningPercentage", ""),
                    "division_rank": t.get("divisionRank"),
                    "games_back": t.get("gamesBack", ""),
                    "streak": (t.get("streak") or {}).get("streakCode", ""),
                    "runs_scored": t.get("runsScored"), "runs_allowed": t.get("runsAllowed"),
                    "run_diff": t.get("runDifferential"),
                    "home_wins": home.get("wins"), "home_losses": home.get("losses"),
                    "away_wins": away.get("wins"), "away_losses": away.get("losses"),
                })
    return out


def classify_matchup(a, b):
    """a, b = team_record dicts. Returns rule-computed matchup type (kills 跨聯盟 error)."""
    if a["league_id"] != b["league_id"]:
        return {"type": "interleague", "zh": "跨聯盟",
                "note": f'{a["name_zh"]}（{LEAGUE_ZH[a["league_id"]]}）vs '
                        f'{b["name_zh"]}（{LEAGUE_ZH[b["league_id"]]}）：分屬不同聯盟'}
    if a["division_id"] == b["division_id"]:
        return {"type": "intra-division", "zh": "分區內對決",
                "note": f'兩隊同屬 {a["division_zh"]}'}
    return {"type": "intra-league-inter-division", "zh": "同聯盟跨分區",
            "note": f'兩隊同屬 {LEAGUE_ZH[a["league_id"]]}（{LEAGUE_EN[a["league_id"]]}），'
                    f'分屬 {a["division_zh"]} 與 {b["division_zh"]}，非跨聯盟'}


def _find_team(recs, key):
    """Match a team by id, full/short en name, abbr, or zh name (substring-tolerant)."""
    s = str(key).strip()
    su = s.upper()
    for r in recs:
        if s in (str(r["team_id"]), r["name"], r.get("name_short", ""), r["name_zh"]) \
                or su == (r.get("abbr") or "").upper():
            return r
    for r in recs:
        if s and (s in r["name"] or s in r["name_zh"] or r.get("name_short", "") in s
                  or bs._norm_name(s) == bs._norm_name(r["name"])):
            return r
    return None


def _ip_decimal(ip):
    """Baseball IP notation 79.2 = 79 + 2/3 → 79.667 for threshold comparison."""
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) + {"": 0, "0": 0, "1": 1 / 3, "2": 2 / 3}.get(frac, 0)
    except Exception:
        return None


def div_tie_leaders(recs):
    """Per division, flag teams tied on pct at the top (kills 白襪「獨居第一」 error)."""
    flags = {}
    by_div = {}
    for r in recs:
        by_div.setdefault(r["division_id"], []).append(r)
    for div, teams in by_div.items():
        teams = sorted(teams, key=lambda t: (-float(t["pct"] or 0), t["division_rank"] or 99))
        top_pct = float(teams[0]["pct"] or 0)
        tied = [t for t in teams if abs(float(t["pct"] or 0) - top_pct) < 1e-9]
        if len(tied) > 1:
            flags[mp.DIV_ZH.get(div, str(div))] = {
                "tied_pct": teams[0]["pct"],
                "teams": [{"name_zh": t["name_zh"], "wins": t["wins"], "losses": t["losses"],
                           "division_rank": t["division_rank"]} for t in tied],
                "note": "並列首位（同勝率），官方分區表依序暫列；勿寫「獨居第一」",
            }
    return flags


# ---------------- builders ----------------

def build_standings_roundup(season, date):
    recs = team_records_asof(season, date)
    by_div = {}
    for r in recs:
        by_div.setdefault(r["division_zh"], []).append(r)
    for k in by_div:
        by_div[k].sort(key=lambda t: (t["division_rank"] or 99))
    boards = {}
    for cat in ("homeRuns", "runsBattedIn"):
        boards[cat] = mp.leaders(cat, season, 10, "hitting")
    for cat in ("earnedRunAverage", "wins"):
        boards[cat] = mp.leaders(cat, season, 10, "pitching")
    return {
        "_type": "standings-roundup", "season": season, "asof": date,
        "source": "MLB StatsAPI /standings (official, reg-season) + /stats/leaders",
        "rule_notes": [
            "standings 為官方權威值；勝差(games_back)直接採官方，勿自行重算",
            "leaders 排行榜對 ERA/AVG 等率定數已自動套規定局數→榜上皆合格者",
            "div_tie_leaders 標出同勝率並列首位的分區→勿寫「獨居第一」",
        ],
        "divisions": by_div,
        "div_tie_leaders": div_tie_leaders(recs),
        "leaderboards_qualified": boards,
    }


def build_game_recap(season, pk):
    box = mp.call(f"/game/{pk}/boxscore")
    line = mp.call(f"/game/{pk}/linescore")
    feed = mp.call(f"/game/{pk}/feed/live") if not box.get("teams") else {}
    teams_box = box.get("teams", {})
    away_name = teams_box.get("away", {}).get("team", {}).get("name", "")
    home_name = teams_box.get("home", {}).get("team", {}).get("name", "")
    recs = team_records_asof(season)  # current; for division/league classification (stable)
    a, h = _find_team(recs, away_name), _find_team(recs, home_name)
    matchup = classify_matchup(a, h) if a and h else {"type": "unknown", "zh": "", "note": ""}
    return {
        "_type": "game-recap", "season": season, "game_pk": pk,
        "source": "MLB StatsAPI /game/{pk}/boxscore + /linescore + /standings",
        "away_name": away_name, "home_name": home_name,
        "away_name_zh": _zh(away_name), "home_name_zh": _zh(home_name),
        "matchup_type": matchup,
        "rule_notes": [f'matchup_type = {matchup["type"]}（{matchup["zh"]}）：{matchup["note"]}',
                       "敘述對決性質一律以 matchup_type 為準，勿用領域知識自行判斷聯盟關係"],
        "linescore": {
            "away_runs": line.get("teams", {}).get("away", {}).get("runs"),
            "home_runs": line.get("teams", {}).get("home", {}).get("runs"),
            "away_hits": line.get("teams", {}).get("away", {}).get("hits"),
            "home_hits": line.get("teams", {}).get("home", {}).get("hits"),
            "away_errors": line.get("teams", {}).get("away", {}).get("errors"),
            "home_errors": line.get("teams", {}).get("home", {}).get("errors"),
        },
        "away_record_asof": {"wins": a["wins"], "losses": a["losses"]} if a else None,
        "home_record_asof": {"wins": h["wins"], "losses": h["losses"]} if h else None,
    }


def build_player_qual(season, pid, team, date):
    pdata = mp.player(pid, season)
    recs = team_records_asof(season, date)
    tr = _find_team(recs, team)
    team_games = (tr["wins"] + tr["losses"]) if tr else None
    pit = pdata.get("pitching", {})
    hit = pdata.get("hitting", {})
    ip = pit.get("inningsPitched")
    ipd = _ip_decimal(ip) if ip else None
    pa = hit.get("plateAppearances")
    out = {
        "_type": "player-qual", "season": season, "asof": date,
        "person_id": pid, "name": pdata.get("name", ""), "team": team,
        "team_games_played": team_games,
        "source": "MLB StatsAPI /people + /standings",
        "rule_notes": [],
    }
    if ipd is not None and team_games:
        q = ipd >= team_games
        out["pitching"] = {
            "era": pit.get("era"), "ip": ip, "ip_decimal": round(ipd, 2),
            "whip": pit.get("whip"), "strikeOuts": pit.get("strikeOuts"),
            "era_title_threshold_ip": team_games,
            "qualified_for_era_title": q,
        }
        out["rule_notes"].append(
            f'ERA 規定局數門檻 = 球隊出賽數 {team_games} 局；本人 {ip}（≈{round(ipd,2)} 局）'
            f'{"已達標→可列官方 ERA 合格榜" if q else "未達標→官方 ERA 合格榜暫無其名，勿寫「全聯盟第N」"}')
    if pa and team_games:
        thr = round(team_games * 3.1, 1)
        q = float(pa) >= thr
        out["hitting"] = {
            "avg": hit.get("avg"), "ops": hit.get("ops"), "homeRuns": hit.get("homeRuns"),
            "plateAppearances": pa, "bat_title_threshold_pa": thr,
            "qualified_for_batting_title": q,
        }
        out["rule_notes"].append(
            f'打擊王規定打席 = 球隊出賽數 ×3.1 ≈ {thr}；本人 {pa} 打席'
            f'{"已達標" if q else "未達標→打擊率排行勿稱「全聯盟第N」"}')
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sr = sub.add_parser("standings-roundup")
    sr.add_argument("--date", required=True); sr.add_argument("--season", type=int)
    gr = sub.add_parser("game-recap")
    gr.add_argument("--pk", type=int, required=True); gr.add_argument("--season", type=int)
    mu = sub.add_parser("matchup")
    mu.add_argument("--home", required=True); mu.add_argument("--away", required=True)
    mu.add_argument("--season", type=int)
    pq = sub.add_parser("player-qual")
    pq.add_argument("--pid", type=int, required=True); pq.add_argument("--team", required=True)
    pq.add_argument("--date", required=True); pq.add_argument("--season", type=int)
    args = ap.parse_args()

    def season_of(a, date=None):
        if getattr(a, "season", None):
            return a.season
        if date:
            return int(date[:4])
        return datetime.date.today().year

    FACTS_DIR.mkdir(exist_ok=True)
    if args.cmd == "standings-roundup":
        season = season_of(args, args.date)
        facts = build_standings_roundup(season, args.date)
        key = f"standings-roundup-{args.date}"
        ties = facts["div_tie_leaders"]
        print(f"📊 standings-roundup {season} @ {args.date}: {sum(len(v) for v in facts['divisions'].values())} teams, "
              f"{len(ties)} 並列首位分區")
        for dv, t in ties.items():
            print(f"   ⚖️ {dv} 並列: " + " / ".join(f"{x['name_zh']} {x['wins']}-{x['losses']}" for x in t["teams"]))
    elif args.cmd == "game-recap":
        season = season_of(args)
        facts = build_game_recap(season, args.pk)
        key = f"game-recap-{args.pk}"
        m = facts["matchup_type"]
        print(f"⚾ game-recap pk={args.pk}: {facts['away_name_zh']} @ {facts['home_name_zh']}")
        print(f"   matchup_type = {m['type']}（{m['zh']}） — {m['note']}")
    elif args.cmd == "matchup":
        season = season_of(args) or datetime.date.today().year
        recs = team_records_asof(season)
        a, h = _find_team(recs, args.away), _find_team(recs, args.home)
        if not a or not h:
            print(f"❌ team not found: away={args.away}({a}) home={args.home}({h})"); return
        m = classify_matchup(a, h)
        facts = {"_type": "matchup", "season": season, "home": h["name_zh"], "away": a["name_zh"],
                 "matchup_type": m}
        key = f"matchup-{a['team_id']}-{h['team_id']}"
        print(f"🆚 {a['name_zh']} vs {h['name_zh']}: {m['type']}（{m['zh']}）")
        print(f"   {m['note']}")
    elif args.cmd == "player-qual":
        season = season_of(args, args.date)
        facts = build_player_qual(season, args.pid, args.team, args.date)
        key = f"player-qual-{args.pid}-{args.date}"
        print(f"🧢 {facts['name']} @ {args.team} ({season}, asof {args.date})")
        for n in facts["rule_notes"]:
            print(f"   • {n}")

    outp = FACTS_DIR / f"{key}.json"
    outp.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ {outp.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
