#!/usr/bin/env python3
"""fetch-league.py — API-Football (api-sports.io) → canonical per-league data file.

Replaces the LLM-web-search data source for structured leagues. Pulls fixtures +
standings + top scorers for one competition (league_id/season from the registry),
normalizes into leagues/<comp>.json — the build/content layers' source of truth.
Facts come from structured JSON, never LLM free-recall (the whole point).

curl backend (framework Python lacks CA certs — [[feedback_framework_python_ssl_cert]]).
Throttled + 429 backoff for the free per-minute burst cap
([[feedback_llm_api_retry_backoff_429]]). All upstream output passes a normalize layer
([[feedback_pipeline_upstream_output_normalize]]) before entering the canonical file.

Usage:
    python3 scripts/fetch-league.py k1            # one competition by registry id
    python3 scripts/fetch-league.py mls --dry-run # print summary, don't write
"""

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://v3.football.api-sports.io"
OUT_DIR = ROOT / "leagues"
SANITY_MAX = 30  # goals per side per match (hallucination/garbage guard, as WC pipeline)

ENV_FILES = [
    pathlib.Path.home() / "Library/CloudStorage/Dropbox/AI/CoWork/meeting-tool/.env",
    pathlib.Path.home() / "Library/CloudStorage/Dropbox/AI/CoWork/worldcup-daily/pipeline.env",
]
FINISHED = {"FT", "AET", "PEN"}  # status.short = match complete -> score is real


def load_key():
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line.startswith("API_FOOTBALL_KEY") and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def load_competition(comp_id):
    reg = json.loads((ROOT / "config" / "competitions.json").read_text(encoding="utf-8"))
    comp = reg.get(comp_id)
    if not comp:
        sys.exit(f"❌ competition '{comp_id}' not in registry")
    ds = comp.get("data_source", {})
    if ds.get("type") != "api-football":
        sys.exit(f"❌ '{comp_id}' data_source is {ds.get('type')}, not api-football")
    return comp, ds["league_id"], ds["season"]


def call(path, key, tries=4):
    delay = 8
    for _ in range(tries):
        out = subprocess.run(
            ["curl", "-sS", "--max-time", "40", "-w", "\n%{http_code}",
             "-H", f"x-apisports-key: {key}", BASE + path],
            capture_output=True, text=True,
        )
        body, _, code = out.stdout.rpartition("\n")
        if code.strip() == "429":
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
        if out.returncode != 0 and not body:
            raise RuntimeError(f"curl rc={out.returncode}: {out.stderr[:120]}")
        data = json.loads(body)
        if data.get("errors"):
            # API returns 200 with an errors object on quota/param problems
            raise RuntimeError(f"api errors: {data['errors']}")
        return data
    raise RuntimeError("429 after retries")


def taipei(dt_iso):
    """ISO8601 (with tz) -> (YYYY-MM-DD, HH:MM) in Asia/Taipei (UTC+8)."""
    try:
        dt = datetime.datetime.fromisoformat(dt_iso)
        tp = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return tp.strftime("%Y-%m-%d"), tp.strftime("%H:%M")
    except Exception:
        return (dt_iso[:10] if dt_iso else ""), ""


# ---------------- normalize ----------------

def norm_matches(raw):
    """API /fixtures response -> canonical matches[]. Scores only kept for FINISHED
    fixtures and within sanity range (never invent/forward-fill)."""
    out, teams = [], {}
    for r in raw:
        fx = r.get("fixture", {})
        lg = r.get("league", {})
        tm = r.get("teams", {})
        g = r.get("goals", {})
        home, away = tm.get("home", {}), tm.get("away", {})
        for t in (home, away):
            if t.get("id") is not None:
                teams[t["id"]] = {"id": t["id"], "name_en": t.get("name", ""),
                                  "logo": t.get("logo", "")}
        date, kickoff = taipei(fx.get("date", ""))
        short = (fx.get("status", {}) or {}).get("short", "")
        m = {
            "id": fx.get("id"),
            "round": lg.get("round", ""),
            "date": date,
            "kickoff_taipei": kickoff,
            "status": short,
            "home_code": str(home.get("id", "")),
            "away_code": str(away.get("id", "")),
            "home_name": home.get("name", ""),
            "away_name": away.get("name", ""),
            "home_iso": "", "away_iso": "",  # leagues use club logos, not flags
        }
        hs, as_ = g.get("home"), g.get("away")
        if short in FINISHED and isinstance(hs, int) and isinstance(as_, int) \
                and 0 <= hs <= SANITY_MAX and 0 <= as_ <= SANITY_MAX:
            m["home_score"] = hs
            m["away_score"] = as_
        out.append(m)
    return out, list(teams.values())


def norm_standings(raw):
    """API /standings -> flat rows (handles multi-group/conference: list of lists)."""
    out = []
    if not raw:
        return out
    groups = raw[0].get("league", {}).get("standings", []) or []
    for grp in groups:
        for row in grp:
            allg = row.get("all", {})
            goals = allg.get("goals", {})
            out.append({
                "rank": row.get("rank"),
                "team_code": str(row.get("team", {}).get("id", "")),
                "team_name": row.get("team", {}).get("name", ""),
                "group": row.get("group", ""),
                "played": allg.get("played", 0),
                "win": allg.get("win", 0),
                "draw": allg.get("draw", 0),
                "lose": allg.get("lose", 0),
                "gf": goals.get("for", 0),
                "ga": goals.get("against", 0),
                "gd": row.get("goalsDiff", 0),
                "points": row.get("points", 0),
            })
    return out


def norm_scorers(raw, limit=20):
    out = []
    for i, r in enumerate(raw[:limit]):
        st = (r.get("statistics") or [{}])[0]
        goals = (st.get("goals") or {}).get("total")
        if not isinstance(goals, int):
            continue
        out.append({
            "rank": i + 1,
            "player": r.get("player", {}).get("name", ""),
            "team_code": str(st.get("team", {}).get("id", "")),
            "team_name": st.get("team", {}).get("name", ""),
            "goals": goals,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("comp_id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--season", type=int, default=None,
                    help="override registry season (Free plan only serves 2022-2024)")
    args = ap.parse_args()

    key = load_key()
    if not key:
        sys.exit("❌ API_FOOTBALL_KEY 找不到（meeting-tool/.env）")
    comp, league_id, season = load_competition(args.comp_id)
    if args.season is not None:
        season = args.season

    print(f"📡 {args.comp_id} (league_id={league_id}, season={season}) …")
    fixtures = call(f"/fixtures?league={league_id}&season={season}", key).get("response", [])
    time.sleep(6)
    standings = call(f"/standings?league={league_id}&season={season}", key).get("response", [])
    time.sleep(6)
    scorers = call(f"/players/topscorers?league={league_id}&season={season}", key).get("response", [])

    matches, teams = norm_matches(fixtures)
    table = norm_standings(standings)
    top = norm_scorers(scorers)
    played = sum(1 for m in matches if "home_score" in m)

    data = {
        "competition": args.comp_id,
        "league_id": league_id,
        "season": season,
        "updated": None,  # stamped by caller / launchd (no Date.now in build)
        "teams": teams,
        "matches": matches,
        "standings": table,
        "scorers": top,
    }
    print(f"   matches={len(matches)} (played={played}) · teams={len(teams)} · "
          f"standings={len(table)} · scorers={len(top)}")
    if top[:3]:
        print("   top3:", ", ".join(f"{s['player']}({s['goals']})" for s in top[:3]))
    if table[:1]:
        t = table[0]
        print(f"   leader: {t['team_name']} {t['points']}pts ({t['win']}-{t['draw']}-{t['lose']})")

    if args.dry_run:
        print("   (dry-run, not writing)")
        return
    OUT_DIR.mkdir(exist_ok=True)
    outp = OUT_DIR / f"{args.comp_id}.json"
    outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ wrote {outp.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
