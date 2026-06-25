#!/usr/bin/env python3
"""fetch-mlb-players.py — MLB StatsAPI (statsapi.mlb.com) → player / roster / leaderboard data.

api-baseball gives team/game/standings/line-score for ALL leagues but has NO player data
(no /players endpoint). For MLB, the official MLB StatsAPI fills that gap: player season
hitting/pitching, team rosters, and league leaderboards (HR/SB/AVG/RBI/OPS/ERA/K/W/SV). It is
free, needs no API key, and is the authoritative source (numbers match MLB.com exactly).

This is the MLB-side of the dual-source baseball data layer:
  api-baseball  -> games, standings, team stats, h2h, line scores   (cross-league)
  MLB StatsAPI  -> players, rosters, leaderboards                    (MLB only)   <-- this file

curl backend (system trust store; framework Python lacks CA certs —
[[feedback_framework_python_ssl_cert]]). All upstream output passes a normalize layer
([[feedback_pipeline_upstream_output_normalize]]) before entering canonical files.

Usage:
    python3 scripts/fetch-mlb-players.py leaders --season 2024     # standard leaderboards -> file
    python3 scripts/fetch-mlb-players.py player 660271 --season 2024   # one player (Ohtani)
    python3 scripts/fetch-mlb-players.py roster 119 --season 2024  # team roster (Dodgers=119)
    python3 scripts/fetch-mlb-players.py linescore --date 2024-09-19   # line scores for a date
"""

import argparse
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://statsapi.mlb.com/api/v1"
OUT_DIR = ROOT / "leagues"
SPORT_MLB = 1

# Standard leaderboard set for data-nerd content (hitting + pitching).
HITTING_CATS = ["homeRuns", "runsBattedIn", "battingAverage", "stolenBases",
                "onBasePlusSlugging", "hits", "runs", "doubles"]
PITCHING_CATS = ["earnedRunAverage", "strikeouts", "wins", "saves", "whip"]
CAT_ZH = {
    "homeRuns": "全壘打", "runsBattedIn": "打點", "battingAverage": "打擊率",
    "stolenBases": "盜壘", "onBasePlusSlugging": "OPS", "hits": "安打", "runs": "得分",
    "doubles": "二壘打", "earnedRunAverage": "自責分率", "strikeouts": "三振",
    "wins": "勝投", "saves": "救援", "whip": "WHIP",
}


def call(path, tries=4):
    delay = 4
    for _ in range(tries):
        out = subprocess.run(
            ["curl", "-sS", "-g", "--max-time", "40", BASE + path],
            capture_output=True, text=True,
        )
        if out.returncode != 0 and not out.stdout:
            time.sleep(delay); delay = min(delay * 2, 30); continue
        try:
            return json.loads(out.stdout)
        except Exception:
            time.sleep(delay); delay = min(delay * 2, 30)
    raise RuntimeError(f"StatsAPI failed after retries: {path}")


# ---------------- normalize ----------------

def teams(season):
    """MLB team id map (StatsAPI ids differ from api-baseball). -> [{id,name,abbr,team_name,division}]"""
    raw = call(f"/teams?sportId={SPORT_MLB}&season={season}").get("teams", [])
    return [{"id": t["id"], "name": t.get("name", ""), "abbr": t.get("abbreviation", ""),
             "team_name": t.get("teamName", ""),
             "division": t.get("division", {}).get("name", "")} for t in raw]


def roster(team_id, season):
    raw = call(f"/teams/{team_id}/roster?season={season}").get("roster", [])
    out = []
    for p in raw:
        out.append({
            "person_id": p.get("person", {}).get("id"),
            "name": p.get("person", {}).get("fullName", ""),
            "number": p.get("jerseyNumber", ""),
            "position": p.get("position", {}).get("abbreviation", ""),
        })
    return out


def player_stats(person_id, season, group):
    """group in {hitting, pitching, fielding}. -> flat stat dict (empty if no split)."""
    d = call(f"/people/{person_id}/stats?stats=season&season={season}&group={group}")
    st = d.get("stats", [])
    if not st or not st[0].get("splits"):
        return {}
    return st[0]["splits"][0].get("stat", {})


def player(person_id, season):
    info = call(f"/people/{person_id}").get("people", [{}])[0]
    return {
        "person_id": person_id,
        "name": info.get("fullName", ""),
        "position": info.get("primaryPosition", {}).get("abbreviation", ""),
        "bats": info.get("batSide", {}).get("code", ""),
        "throws": info.get("pitchHand", {}).get("code", ""),
        "season": season,
        "hitting": player_stats(person_id, season, "hitting"),
        "pitching": player_stats(person_id, season, "pitching"),
    }


def leaders(category, season, limit=10, group="hitting"):
    d = call(f"/stats/leaders?leaderCategories={category}&season={season}"
             f"&sportId={SPORT_MLB}&statGroup={group}&limit={limit}")
    blocks = d.get("leagueLeaders", [])
    if not blocks:
        return []
    rows = blocks[0].get("leaders", [])
    return [{"rank": r.get("rank"), "name": r.get("person", {}).get("fullName", ""),
             "team": r.get("team", {}).get("name", ""), "value": r.get("value")}
            for r in rows]


def linescores(date):
    """All MLB games on a date with line score (R-H-E + per-inning). date = YYYY-MM-DD."""
    d = call(f"/schedule?sportId={SPORT_MLB}&date={date}&hydrate=linescore")
    out = []
    for day in d.get("dates", []):
        for g in day.get("games", []):
            ls = g.get("linescore", {})
            t = ls.get("teams", {})
            innings = [{"num": i.get("num"), "home": i.get("home", {}).get("runs"),
                        "away": i.get("away", {}).get("runs")} for i in ls.get("innings", [])]
            out.append({
                "date": date,
                "away_name": g["teams"]["away"]["team"]["name"],
                "home_name": g["teams"]["home"]["team"]["name"],
                "away": {"r": t.get("away", {}).get("runs"), "h": t.get("away", {}).get("hits"),
                         "e": t.get("away", {}).get("errors")},
                "home": {"r": t.get("home", {}).get("runs"), "h": t.get("home", {}).get("hits"),
                         "e": t.get("home", {}).get("errors")},
                "innings": innings,
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("leaders"); pl.add_argument("--season", type=int, required=True)
    pp = sub.add_parser("player"); pp.add_argument("person_id", type=int); pp.add_argument("--season", type=int, required=True)
    pr = sub.add_parser("roster"); pr.add_argument("team_id", type=int); pr.add_argument("--season", type=int, required=True)
    pls = sub.add_parser("linescore"); pls.add_argument("--date", required=True)
    args = ap.parse_args()

    if args.cmd == "leaders":
        data = {"season": args.season, "hitting": {}, "pitching": {}}
        for c in HITTING_CATS:
            data["hitting"][c] = leaders(c, args.season, 10, "hitting"); time.sleep(1)
        for c in PITCHING_CATS:
            data["pitching"][c] = leaders(c, args.season, 10, "pitching"); time.sleep(1)
        outp = OUT_DIR / f"mlb-leaders-{args.season}.json"
        OUT_DIR.mkdir(exist_ok=True)
        outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ {outp.relative_to(ROOT)}")
        for c in HITTING_CATS[:4]:
            top = data["hitting"][c][:3]
            print(f"   {CAT_ZH[c]}: " + ", ".join(f"{r['name']}({r['value']})" for r in top))

    elif args.cmd == "player":
        p = player(args.person_id, args.season)
        h = p["hitting"]
        print(f"{p['name']} ({p['position']}) {args.season}: "
              f"HR {h.get('homeRuns')} RBI {h.get('rbi')} AVG {h.get('avg')} "
              f"SB {h.get('stolenBases')} OPS {h.get('ops')}")
        print(json.dumps(p, ensure_ascii=False, indent=2))

    elif args.cmd == "roster":
        r = roster(args.team_id, args.season)
        print(f"roster {args.team_id} {args.season}: {len(r)} players")
        for p in r[:8]:
            print(f"  {p['number']:>3} {p['name']} ({p['position']})")

    elif args.cmd == "linescore":
        for g in linescores(args.date):
            a, h = g["away"], g["home"]
            print(f"{g['away_name']} {a['r']}-{a['h']}-{a['e']} @ "
                  f"{g['home_name']} {h['r']}-{h['h']}-{h['e']}  ({len(g['innings'])} inn)")


if __name__ == "__main__":
    main()
