#!/usr/bin/env python3
"""
gen-ics.py — 從 fixtures/group-stage.json (+ knockout.json) 生 48 隊 ICS + 全程 ICS

輸出：
  public/cal/POR.ics, BRA.ics, ... × 48
  public/cal/tournament.ics（全 104 場一起）

ICS 規格：RFC 5545，DTSTART 用 TZID=Asia/Taipei，SUMMARY 中文 + 國旗 emoji。

用法：
    python3 scripts/gen-ics.py
"""

import datetime
import json
import pathlib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
OUT = ROOT / "public" / "cal"
OUT.mkdir(parents=True, exist_ok=True)


# 中文國名 map (FIFA 3-letter code → 中文簡稱) — 給 ICS SUMMARY 用
TEAM_ZH = {
    "ARG": "阿根廷", "AUS": "澳洲", "AUT": "奧地利", "BEL": "比利時",
    "BIH": "波士尼亞", "BRA": "巴西", "CAN": "加拿大", "CIV": "象牙海岸",
    "COD": "民主剛果", "COL": "哥倫比亞", "CPV": "維德角", "CRO": "克羅埃西亞",
    "CUW": "古拉索", "CZE": "捷克", "ECU": "厄瓜多", "EGY": "埃及",
    "ENG": "英格蘭", "ESP": "西班牙", "FRA": "法國", "GER": "德國",
    "GHA": "迦納", "HAI": "海地", "IRN": "伊朗", "IRQ": "伊拉克",
    "JOR": "約旦", "JPN": "日本", "KOR": "南韓", "KSA": "沙烏地阿拉伯",
    "MAR": "摩洛哥", "MEX": "墨西哥", "NED": "荷蘭", "NOR": "挪威",
    "NZL": "紐西蘭", "PAN": "巴拿馬", "PAR": "巴拉圭", "POR": "葡萄牙",
    "QAT": "卡達", "RSA": "南非", "SCO": "蘇格蘭", "SEN": "塞內加爾",
    "SUI": "瑞士", "SWE": "瑞典", "TUN": "突尼西亞", "TUR": "土耳其",
    "URU": "烏拉圭", "USA": "美國", "UZB": "烏茲別克", "ALG": "阿爾及利亞",
}


def flag_emoji(iso2: str) -> str:
    """ISO-3166 alpha-2 → 🇹🇼 style emoji (regional indicator symbols)"""
    if not iso2 or len(iso2) != 2:
        return ""
    a = ord(iso2.upper()[0]) - ord("A") + 0x1F1E6
    b = ord(iso2.upper()[1]) - ord("A") + 0x1F1E6
    return chr(a) + chr(b)


def parse_kickoff(date_str: str, kickoff_taipei: str) -> datetime.datetime:
    """
    date_str: "2026-06-17" (北美當地日期)
    kickoff_taipei: "01:00+1" or "12:00" — 台北時間，+1 表示日期跨日 +1 天
    回傳 naive datetime (台北時區語意)
    """
    days_offset = 0
    if "+" in kickoff_taipei:
        time_part, _, offset_part = kickoff_taipei.partition("+")
        days_offset = int(offset_part)
    else:
        time_part = kickoff_taipei
    hh, mm = time_part.split(":")
    base_date = datetime.date.fromisoformat(date_str)
    return datetime.datetime.combine(base_date + datetime.timedelta(days=days_offset),
                                     datetime.time(int(hh), int(mm)))


def ics_escape(text: str) -> str:
    """RFC 5545 §3.3.11 TEXT escaping"""
    return text.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def fmt_dt(dt: datetime.datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def build_vevent(match: dict, dtstamp: str) -> str:
    start = parse_kickoff(match["date"], match["kickoff_taipei"])
    end = start + datetime.timedelta(hours=2)  # 90min + HT + 補時 ≈ 2h
    home_emoji = flag_emoji(match["home_iso"])
    away_emoji = flag_emoji(match["away_iso"])
    home_zh = TEAM_ZH.get(match["home_code"], match["home_team"])
    away_zh = TEAM_ZH.get(match["away_code"], match["away_team"])
    summary = f"{home_emoji} {home_zh} vs {away_emoji} {away_zh} (Group {match['group']})"
    location = f"{match['stadium']}, {match['city']}"
    taipei_disp = start.strftime("%Y-%m-%d %H:%M")
    et_disp = f"{match['date']} {match['kickoff_et']}"
    description = (
        f"Match #{match['match_no']} | Group {match['group']} | 2026 FIFA World Cup\\n"
        f"開球：台北 {taipei_disp}（北美 {et_disp} ET）\\n"
        f"場館：{location}\\n"
        f"\\n"
        f"📺 台灣直播：愛爾達 https://eltaott.tv／中華電信 MOD 200-203（愛爾達體育 1-4 台）／Hami Video\\n"
        f"🎁 部分場次 華視 12 免費播（開幕前公布逐場 schedule）\\n"
        f"🌏 海外觀眾請查當地轉播平台"
    )
    uid = f"wc2026-match-{match['match_no']:03d}@foootball.twtools.cc"
    url = f"https://foootball.twtools.cc/teams/{match['home_code']}"

    return "\r\n".join([
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{dtstamp}",
        f"DTSTART;TZID=Asia/Taipei:{fmt_dt(start)}",
        f"DTEND;TZID=Asia/Taipei:{fmt_dt(end)}",
        f"SUMMARY:{ics_escape(summary)}",
        f"LOCATION:{ics_escape(location)}",
        f"DESCRIPTION:{description}",
        f"URL:{url}",
        "END:VEVENT",
    ])


TIMEZONE_BLOCK = "\r\n".join([
    "BEGIN:VTIMEZONE",
    "TZID:Asia/Taipei",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0800",
    "TZOFFSETTO:+0800",
    "TZNAME:CST",
    "END:STANDARD",
    "END:VTIMEZONE",
])


def build_vcalendar(matches: list, calname: str, caldesc: str, dtstamp: str) -> str:
    parts = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//foootball.twtools.cc//World Cup 2026//ZH-TW",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calname)}",
        f"X-WR-CALDESC:{ics_escape(caldesc)}",
        "X-WR-TIMEZONE:Asia/Taipei",
        TIMEZONE_BLOCK,
    ]
    for m in matches:
        parts.append(build_vevent(m, dtstamp))
    parts.append("END:VCALENDAR")
    return "\r\n".join(parts) + "\r\n"


def main():
    fixtures_path = FIXTURES / "group-stage.json"
    all_matches = json.loads(fixtures_path.read_text(encoding="utf-8"))
    knockout_path = FIXTURES / "knockout.json"
    if knockout_path.exists():
        all_matches += json.loads(knockout_path.read_text(encoding="utf-8"))

    # 依 ISO 8601 timestamp（fetch 當下，hardcode 進每個 VEVENT DTSTAMP）
    # 為了 deterministic build（Cloudflare Pages re-deploy 不會變 DTSTAMP），用 fixtures.json mtime
    mtime = fixtures_path.stat().st_mtime
    dtstamp = datetime.datetime.utcfromtimestamp(mtime).strftime("%Y%m%dT%H%M%SZ")

    # 過濾 placeholder 場次（淘汰賽抽完前 home_code/away_code 缺失）
    renderable = [
        m for m in all_matches
        if m.get("home_code") and m.get("away_code")
        and m.get("kickoff_taipei") and m.get("home_iso") and m.get("away_iso")
    ]
    skipped = len(all_matches) - len(renderable)
    if skipped:
        print(f"   ⏭️  skip {skipped} placeholder 場次（淘汰賽未抽完 / 缺欄位）")

    # 按 team code group matches
    by_team = defaultdict(list)
    for m in renderable:
        by_team[m["home_code"]].append(m)
        by_team[m["away_code"]].append(m)

    # 每隊一個 ICS
    for code, matches in by_team.items():
        matches_sorted = sorted(matches, key=lambda x: (x["date"], x["kickoff_taipei"]))
        zh = TEAM_ZH.get(code, code)
        calname = f"{flag_emoji(matches_sorted[0]['home_iso' if matches_sorted[0]['home_code']==code else 'away_iso'])} {zh} 世界盃 2026"
        caldesc = f"{zh}（{code}）在 2026 美加墨 FIFA 世界盃的全部賽程，台北時間自動換算。"
        ics_text = build_vcalendar(matches_sorted, calname, caldesc, dtstamp)
        (OUT / f"{code}.ics").write_text(ics_text, encoding="utf-8")

    # 全程 tournament.ics（只含 renderable 場次，淘汰賽抽完逐輪 fill in）
    all_sorted = sorted(renderable, key=lambda x: (x["date"], x["kickoff_taipei"]))
    tournament_ics = build_vcalendar(
        all_sorted,
        "2026 美加墨世界盃完整賽程",
        "2026 FIFA World Cup full schedule — 台北時間 / 自動同步。",
        dtstamp,
    )
    (OUT / "tournament.ics").write_text(tournament_ics, encoding="utf-8")

    print(f"✅ 寫出 {len(by_team)} 隊 + 1 個 tournament.ics → {OUT}")
    print(f"   範例：{sorted(by_team)[:5]} … {sorted(by_team)[-5:]}")


if __name__ == "__main__":
    main()
