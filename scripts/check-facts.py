#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check-facts.py — independent second-source QA for baseball deep articles.

Why (2026-06-26 retro): the old Opus QA grepped article numbers against the SAME facts pack
that fed the writer — circular. If the facts were wrong (tonight's standings 44-33 vs official
45-33), the QA validated the error. This script verifies against an INDEPENDENT re-pull from
the official source (MLB StatsAPI), so a wrong-facts error surfaces *before* the human.

Checks:
  verify-standings  re-pull official standings @date, diff every team row in the article's
                    markdown tables (W / L / pct / RD). Catches stale/computed-wrong standings.
  matchup-check     classify the official matchup (league/division) and flag any contradicting
                    「跨聯盟 / interleague」claim in the article. Catches the 跨聯盟 class.
  numbers-in-facts  extract table-cell numbers; flag those absent from the facts pack JSON
                    (transcription / fabrication). Lower signal, table-scoped to cut noise.

Exit code 1 if any MISMATCH/contradiction is found (usable as a publish gate).

Usage:
  python3 scripts/check-facts.py verify-standings --article articles/<slug>/index.md --date 2026-06-25
  python3 scripts/check-facts.py matchup-check --article articles/<slug>/index.md --home "..." --away "..."
  python3 scripts/check-facts.py numbers-in-facts --article articles/<slug>/index.md --facts facts/<x>.json
"""
import argparse
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / fname)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


bf = _load("build_facts", "build-facts.py")


def _rows(md):
    """Yield list-of-cells for every markdown table row in the article."""
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("|") and s.count("|") >= 3:
            cells = [c.strip().replace("**", "") for c in s.strip("|").split("|")]
            yield cells


# ---------------- verify-standings ----------------

def verify_standings(article, season, date):
    md = pathlib.Path(article).read_text(encoding="utf-8")
    recs = bf.team_records_asof(season, date)
    by_zh = {r["name_zh"]: r for r in recs}
    mism, checked = [], 0
    for cells in _rows(md):
        team = cells[0]
        rec = by_zh.get(team) or next((r for z, r in by_zh.items() if z and z in team), None)
        if not rec:
            continue
        nums = " ".join(cells[1:])
        ints = re.findall(r"(?<![.\d])(\d{1,3})(?![.\d])", nums)        # bare ints: W, L first
        pcts = re.findall(r"\.(\d{3})", nums)                            # .577
        rds = re.findall(r"([+-]\d{1,3})(?![.\d])", nums)               # +13 / -49
        if len(ints) < 2:
            continue
        checked += 1
        w, l = int(ints[0]), int(ints[1])
        if (w, l) != (rec["wins"], rec["losses"]):
            mism.append(f"{team}: 文章 {w}-{l} ✗ 官方 {rec['wins']}-{rec['losses']}")
        if pcts:
            a_pct = f".{pcts[0]}"
            o_pct = str(rec["pct"]).lstrip("0") or rec["pct"]
            if a_pct != o_pct:
                mism.append(f"{team}: 勝率 文章 {a_pct} ✗ 官方 {rec['pct']}")
        if rds:
            a_rd = int(rds[-1])
            if a_rd != rec["run_diff"]:
                mism.append(f"{team}: RD 文章 {a_rd:+d} ✗ 官方 {rec['run_diff']:+d}")
    print(f"📊 verify-standings @ {date}: 比對 {checked} 隊列 vs 官方 StatsAPI")
    if mism:
        print(f"❌ {len(mism)} 處不符：")
        for m in mism:
            print(f"   ✗ {m}")
        return False
    print("✅ 所有出現在表格的球隊 W-L / 勝率 / RD 皆與官方一致")
    return True


# ---------------- matchup-check ----------------

def matchup_check(article, season, home, away):
    md = pathlib.Path(article).read_text(encoding="utf-8")
    recs = bf.team_records_asof(season)
    a, h = bf._find_team(recs, away), bf._find_team(recs, home)
    if not a or not h:
        print(f"❌ team not found: away={away} home={home}"); return False
    m = bf.classify_matchup(a, h)
    print(f"🆚 官方判定：{a['name_zh']} vs {h['name_zh']} = {m['type']}（{m['zh']}）")
    # 只抓「肯定」的跨聯盟主張；「非/並非/不是/而非跨聯盟」是正確否定，不算矛盾。
    def _affirms_interleague(ln):
        low = ln.lower()
        if "跨聯盟" not in ln and "interleague" not in low:
            return False
        return not re.search(r"(非|並非|不是|而非|不屬)跨聯盟", ln)
    hits = [ln.strip() for ln in md.splitlines() if _affirms_interleague(ln)]
    if m["type"] != "interleague" and hits:
        print(f"❌ 文章含「跨聯盟」字樣 {len(hits)} 處，但官方為「{m['zh']}」——矛盾：")
        for ln in hits[:5]:
            print(f"   ✗ {ln[:70]}…")
        return False
    if m["type"] == "interleague" and not hits:
        print("⚠️ 官方為跨聯盟，但文章未點明（非錯誤，提示）")
    print("✅ 對決性質敘述與官方一致")
    return True


# ---------------- numbers-in-facts ----------------

def _norm_num(tok):
    """Normalize a numeric token for set membership: drop leading +, leading zeros,
    and a leading 0 before a decimal point (so .476 == 0.476, +13 == 13)."""
    t = str(tok).strip().lstrip("+")
    if t.startswith("0.") or t.startswith("-0."):
        t = t.replace("0.", ".", 1)
    if t and t.lstrip("-") and "." not in t:
        sign = "-" if t.startswith("-") else ""
        t = sign + (t.lstrip("-").lstrip("0") or "0")
    return t


def _flatten_nums(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _flatten_nums(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _flatten_nums(v, acc)
    elif isinstance(obj, (int, float)):
        acc.add(_norm_num(obj))
    elif isinstance(obj, str):
        for tok in re.findall(r"[-+]?\d+(?:\.\d+)?", obj):
            acc.add(_norm_num(tok))


def numbers_in_facts(article, facts):
    md = pathlib.Path(article).read_text(encoding="utf-8")
    fk = set()
    _flatten_nums(json.loads(pathlib.Path(facts).read_text(encoding="utf-8")), fk)
    orphan = set()
    for cells in _rows(md):
        for c in cells:
            for tok in re.findall(r"[-+]?\d+(?:\.\d+)?", c):
                n = _norm_num(tok)
                if n not in fk and len(n.lstrip("-+")) >= 2:   # 略過個位數(噪音)
                    orphan.add(tok)
    print(f"🔢 numbers-in-facts（提示性，非 gate）：表格數字比對 facts pack {pathlib.Path(facts).name}")
    if orphan:
        print(f"⚠️ {len(orphan)} 個表格數字不在此 facts pack（可能抄寫錯/捏造，或 facts pack 不含該型數據，需人工掃一眼）：")
        print("   " + ", ".join(sorted(orphan, key=lambda x: (len(x), x))[:30]))
    else:
        print("✅ 表格數字皆可在 facts pack 找到")
    return True  # 提示性檢查，永遠不擋 gate（高價值 gate 是 verify-standings / matchup-check）


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    vs = sub.add_parser("verify-standings")
    vs.add_argument("--article", required=True); vs.add_argument("--date", required=True)
    vs.add_argument("--season", type=int)
    mc = sub.add_parser("matchup-check")
    mc.add_argument("--article", required=True); mc.add_argument("--home", required=True)
    mc.add_argument("--away", required=True); mc.add_argument("--season", type=int)
    nf = sub.add_parser("numbers-in-facts")
    nf.add_argument("--article", required=True); nf.add_argument("--facts", required=True)
    args = ap.parse_args()

    if args.cmd == "verify-standings":
        ok = verify_standings(args.article, args.season or int(args.date[:4]), args.date)
    elif args.cmd == "matchup-check":
        import datetime
        ok = matchup_check(args.article, args.season or datetime.date.today().year,
                           args.home, args.away)
    elif args.cmd == "numbers-in-facts":
        ok = numbers_in_facts(args.article, args.facts)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
