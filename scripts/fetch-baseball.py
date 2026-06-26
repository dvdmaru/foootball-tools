#!/usr/bin/env python3
"""fetch-baseball.py — API-Baseball (api-sports.io) → canonical per-league data file.

Baseball sibling of fetch-league.py. Same api-sports account key (account-level), different
host (v1.baseball) and response shape: /games (not /fixtures), scores.{home,away}.total (not
goals). The /standings endpoint is a DEAD END for baseball (CPBL: results=0; MLB/NPB/KBO: rows
present but games/win/lose all 0) — so standings are COMPUTED from finished results, the source
of truth: W/L, winning pct (ties excluded from denominator), games-behind. No draw, no run-diff.

Facts come from structured JSON, never LLM free-recall (the whole point). curl backend
(framework Python lacks CA certs — [[feedback_framework_python_ssl_cert]]); throttle + 429
backoff for the free per-minute burst cap ([[feedback_llm_api_retry_backoff_429]]); all
upstream output passes a normalize layer ([[feedback_pipeline_upstream_output_normalize]]).

Usage:
    python3 scripts/fetch-baseball.py cpbl              # registry id (season from registry)
    python3 scripts/fetch-baseball.py mlb --season 2024 # override season (Free = historical)
    python3 scripts/fetch-baseball.py cpbl --dry-run    # print summary, don't write
"""

import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://v1.baseball.api-sports.io"
OUT_DIR = ROOT / "leagues"
SANITY_MAX = 40  # runs per side per game (blowouts happen; this only guards garbage/hallucination)

ENV_FILES = [
    pathlib.Path.home() / "Library/CloudStorage/Dropbox/AI/CoWork/meeting-tool/.env",
    pathlib.Path.home() / "Library/CloudStorage/Dropbox/AI/CoWork/worldcup-daily/pipeline.env",
]
FINISHED = {"FT", "AOT"}  # status.short = game complete (incl. extra innings) -> score is real
# api-baseball mixes the All-Star Game into /games as pseudo-teams ("American League" vs
# "National League"). They are not clubs -> drop those games so they never pollute standings.
NON_CLUB = {"american league", "national league", "world", "all stars", "all-stars"}


def _is_club(name):
    n = (name or "").strip().lower()
    return bool(n) and n not in NON_CLUB and "all-star" not in n and "all star" not in n


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
    if ds.get("type") != "api-baseball":
        sys.exit(f"❌ '{comp_id}' data_source is {ds.get('type')}, not api-baseball")
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
        dt = datetime.datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
        tp = dt.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        return tp.strftime("%Y-%m-%d"), tp.strftime("%H:%M")
    except Exception:
        return (dt_iso[:10] if dt_iso else ""), ""


# ---------------- normalize ----------------

def norm_games(raw):
    """API /games response -> canonical games[]. Scores only kept for FINISHED games and
    within sanity range (never invent/forward-fill). No draws/goal-diff (baseball)."""
    out, teams = [], {}
    for r in raw:
        lg_round = r.get("stage") or (r.get("league", {}) or {}).get("season", "")
        tm = r.get("teams", {})
        sc = r.get("scores", {})
        home, away = tm.get("home", {}) or {}, tm.get("away", {}) or {}
        if not (_is_club(home.get("name")) and _is_club(away.get("name"))):
            continue  # All-Star Game (league-vs-league) — not a real club fixture
        for t in (home, away):
            if t.get("id") is not None:
                teams[t["id"]] = {"id": t["id"], "name_en": t.get("name", ""),
                                  "logo": t.get("logo", "")}
        date, first_pitch = taipei(r.get("date", ""))
        short = (r.get("status", {}) or {}).get("short", "")
        m = {
            "id": r.get("id"),
            "round": str(lg_round),
            "date": date,
            "first_pitch_taipei": first_pitch,
            "status": short,
            "home_code": str(home.get("id", "")),
            "away_code": str(away.get("id", "")),
            "home_name": home.get("name", ""),
            "away_name": away.get("name", ""),
        }
        hs = (sc.get("home") or {}).get("total")
        as_ = (sc.get("away") or {}).get("total")
        if short in FINISHED and isinstance(hs, int) and isinstance(as_, int) \
                and 0 <= hs <= SANITY_MAX and 0 <= as_ <= SANITY_MAX:
            m["home_score"] = hs
            m["away_score"] = as_
        out.append(m)
    return out, list(teams.values())


def compute_standings(games):
    """Derive standings from FINISHED game results — the api-baseball /standings endpoint is a
    dead end (CPBL: results=0; MLB/NPB/KBO: rows present but games/win/lose all 0, ranked by
    team id). Results are the source of truth. Overall league table: W/L, winning pct (ties
    excluded from the denominator, per baseball convention — NPB allows ties), games-behind vs
    the leader. Division/split-season grouping is a later (Phase D) presentation layer."""
    rec = {}
    for g in games:
        if "home_score" not in g or "away_score" not in g:
            continue
        hc, ac = g["home_code"], g["away_code"]
        rec.setdefault(hc, {"team_code": hc, "team_name": g["home_name"], "win": 0, "lose": 0})
        rec.setdefault(ac, {"team_code": ac, "team_name": g["away_name"], "win": 0, "lose": 0})
        hs, as_ = g["home_score"], g["away_score"]
        if hs > as_:
            rec[hc]["win"] += 1; rec[ac]["lose"] += 1
        elif as_ > hs:
            rec[ac]["win"] += 1; rec[hc]["lose"] += 1
        # tie (NPB 引分): counts as neither a win nor a loss
    rows = list(rec.values())
    for r in rows:
        decided = r["win"] + r["lose"]
        r["played"] = decided
        r["group"] = ""
        r["pct"] = f"{r['win'] / decided:.3f}" if decided else "0.000"
    rows.sort(key=lambda r: (-r["win"], r["lose"], r["team_name"]))
    if rows:
        lw, ll = rows[0]["win"], rows[0]["lose"]
        for i, r in enumerate(rows):
            r["rank"] = i + 1
            gb = ((lw - r["win"]) + (r["lose"] - ll)) / 2
            r["games_behind"] = 0.0 if gb <= 0 else round(gb, 1)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("comp_id")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--season", type=int, default=None,
                    help="override registry season (Free plan only serves historical seasons)")
    args = ap.parse_args()

    key = load_key()
    if not key:
        sys.exit("❌ API_FOOTBALL_KEY 找不到（meeting-tool/.env；api-sports 帳號層共用同一把）")
    comp, league_id, season = load_competition(args.comp_id)
    if args.season is not None:
        season = args.season

    print(f"📡 {args.comp_id} (league_id={league_id}, season={season}) …")
    games_raw = call(f"/games?league={league_id}&season={season}", key).get("response", [])

    games, teams = norm_games(games_raw)
    table = compute_standings(games)  # /standings endpoint is empty for baseball — derive from results
    played = sum(1 for m in games if "home_score" in m)

    data = {
        "competition": args.comp_id,
        "sport": "baseball",
        "league_id": league_id,
        "season": season,
        "updated": None,  # stamped by caller / launchd (no Date.now in build)
        "teams": teams,
        "games": games,
        "standings": table,
    }
    print(f"   games={len(games)} (played={played}) · teams={len(teams)} · standings={len(table)}")
    if table[:1]:
        t = table[0]
        print(f"   leader: {t['team_name']} {t['win']}-{t['lose']} "
              f"(pct {t['pct']}, GB {t['games_behind']}, group {t['group'] or '—'})")

    if args.dry_run:
        print("   (dry-run, not writing)")
        return
    OUT_DIR.mkdir(exist_ok=True)
    outp = OUT_DIR / f"{args.comp_id}.json"
    outp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   ✅ wrote {outp.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
