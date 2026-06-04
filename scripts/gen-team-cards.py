#!/usr/bin/env python3
"""
gen-team-cards.py — 從 fixtures/group-stage.json 生 by-team IG/FB 賽程卡 PNG

每隊一張 1080x1350 (4:5 IG feed) PNG，含：
  - 國旗 emoji + 中文國名 + 英文/三碼
  - Group X · 小組賽 3 場 chip
  - 3 場 group stage row（日期/週幾/台北時間 + 對手國旗+中文名 + 場館城市 + 主客場 tag）
  - footer：訂閱整季 CTA + foootball.twtools.cc + @foootball

用法：
    python3 scripts/gen-team-cards.py           # 全 48 隊
    python3 scripts/gen-team-cards.py POR       # 單張（prototype 用）
    python3 scripts/gen-team-cards.py POR BRA   # 多隊
"""

import datetime
import html as html_lib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
TEMPLATE = ROOT / "templates" / "team-card.html"
OUT = ROOT / "public" / "cards"
OUT.mkdir(parents=True, exist_ok=True)

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 與 gen-ics.py 共用同一張中文名表
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

# 三碼 → 英文全名（顯示在中文名下方小字）
TEAM_EN = {
    "ARG": "ARGENTINA", "AUS": "AUSTRALIA", "AUT": "AUSTRIA", "BEL": "BELGIUM",
    "BIH": "BOSNIA & HERZEGOVINA", "BRA": "BRAZIL", "CAN": "CANADA", "CIV": "CÔTE D'IVOIRE",
    "COD": "DR CONGO", "COL": "COLOMBIA", "CPV": "CAPE VERDE", "CRO": "CROATIA",
    "CUW": "CURAÇAO", "CZE": "CZECHIA", "ECU": "ECUADOR", "EGY": "EGYPT",
    "ENG": "ENGLAND", "ESP": "SPAIN", "FRA": "FRANCE", "GER": "GERMANY",
    "GHA": "GHANA", "HAI": "HAITI", "IRN": "IRAN", "IRQ": "IRAQ",
    "JOR": "JORDAN", "JPN": "JAPAN", "KOR": "SOUTH KOREA", "KSA": "SAUDI ARABIA",
    "MAR": "MOROCCO", "MEX": "MEXICO", "NED": "NETHERLANDS", "NOR": "NORWAY",
    "NZL": "NEW ZEALAND", "PAN": "PANAMA", "PAR": "PARAGUAY", "POR": "PORTUGAL",
    "QAT": "QATAR", "RSA": "SOUTH AFRICA", "SCO": "SCOTLAND", "SEN": "SENEGAL",
    "SUI": "SWITZERLAND", "SWE": "SWEDEN", "TUN": "TUNISIA", "TUR": "TÜRKİYE",
    "URU": "URUGUAY", "USA": "USA", "UZB": "UZBEKISTAN", "ALG": "ALGERIA",
}

WEEKDAY_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


def flag_emoji(iso2: str) -> str:
    if not iso2 or len(iso2) != 2:
        return ""
    a = ord(iso2.upper()[0]) - ord("A") + 0x1F1E6
    b = ord(iso2.upper()[1]) - ord("A") + 0x1F1E6
    return chr(a) + chr(b)


def parse_taipei_dt(date_str: str, kickoff_taipei: str):
    """date_str=北美當地日期, kickoff_taipei='01:00+1' or '12:00'
    回傳 (datetime, time_str_HHMM, date_str_YYYY/MM/DD)"""
    days_offset = 0
    if "+" in kickoff_taipei:
        time_part, _, offset_part = kickoff_taipei.partition("+")
        days_offset = int(offset_part)
    else:
        time_part = kickoff_taipei
    hh, mm = time_part.split(":")
    base = datetime.date.fromisoformat(date_str) + datetime.timedelta(days=days_offset)
    dt = datetime.datetime.combine(base, datetime.time(int(hh), int(mm)))
    return dt, f"{int(hh):02d}:{int(mm):02d}", base.strftime("%Y/%m/%d")


def build_match_row(match: dict, this_code: str) -> str:
    dt, time_str, date_str = parse_taipei_dt(match["date"], match["kickoff_taipei"])
    weekday = WEEKDAY_ZH[dt.weekday()]
    is_home = match["home_code"] == this_code
    if is_home:
        opp_code = match["away_code"]
        opp_iso = match["away_iso"]
        opp_team_raw = match["away_team"]
        tag_html = '<span class="home-tag home">主場</span>'
    else:
        opp_code = match["home_code"]
        opp_iso = match["home_iso"]
        opp_team_raw = match["home_team"]
        tag_html = '<span class="home-tag away">客場</span>'
    opp_zh = TEAM_ZH.get(opp_code, opp_team_raw)
    opp_flag = flag_emoji(opp_iso)

    return f"""
    <div class="match">
      <div class="date-col">
        <div class="date">{date_str}<span class="weekday">{weekday}</span></div>
        <div class="time">{time_str}</div>
        <div class="tz">TAIPEI · UTC+8</div>
      </div>
      <div class="vs-col">
        <div class="vs-label">VS</div>
        <div class="opp">
          <span class="opp-flag">{opp_flag}</span>
          <span class="opp-name">{html_lib.escape(opp_zh)}</span>
        </div>
      </div>
      <div class="venue-col">
        {tag_html}
        <div class="stadium">{html_lib.escape(match["stadium"])}</div>
        <div class="city">{html_lib.escape(match["city"])}</div>
      </div>
    </div>
    """


def render_html(code: str, matches: list) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    iso = matches[0]["home_iso"] if matches[0]["home_code"] == code else matches[0]["away_iso"]
    zh = TEAM_ZH.get(code, code)
    en = TEAM_EN.get(code, code)
    group = matches[0]["group"]
    matches_sorted = sorted(matches, key=lambda x: (x["date"], x["kickoff_taipei"]))
    matches_html = "".join(build_match_row(m, code) for m in matches_sorted)
    return (template
            .replace("{{FLAG}}", flag_emoji(iso))
            .replace("{{NAME_ZH}}", html_lib.escape(zh))
            .replace("{{NAME_EN}}", html_lib.escape(en))
            .replace("{{CODE}}", code)
            .replace("{{GROUP}}", group)
            .replace("{{MATCHES_HTML}}", matches_html))


def screenshot(html_path: pathlib.Path, png_path: pathlib.Path):
    """Chrome headless → PNG. force-device-scale-factor=2 = retina 2160x2700."""
    cmd = [
        CHROME,
        "--headless",
        "--disable-gpu",
        "--hide-scrollbars",
        f"--screenshot={png_path}",
        "--window-size=1080,1350",
        "--force-device-scale-factor=2",
        "--default-background-color=00000000",
        "--virtual-time-budget=5000",
        f"file://{html_path}",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not png_path.exists():
        print("Chrome stderr:", res.stderr, file=sys.stderr)
        raise RuntimeError(f"screenshot failed for {png_path.name}")


def gen_one(code: str, by_team: dict):
    matches = by_team.get(code)
    if not matches:
        print(f"⚠️  {code}: no matches, skip")
        return False
    html = render_html(code, matches)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        html_path = pathlib.Path(f.name)
    try:
        png_path = OUT / f"{code}.png"
        screenshot(html_path, png_path)
        print(f"✅ {code} → {png_path.relative_to(ROOT)}")
        return True
    finally:
        html_path.unlink(missing_ok=True)


def main():
    fixtures = json.loads((FIXTURES / "group-stage.json").read_text(encoding="utf-8"))
    by_team = defaultdict(list)
    for m in fixtures:
        if m.get("home_code") and m.get("away_code"):
            by_team[m["home_code"]].append(m)
            by_team[m["away_code"]].append(m)

    targets = [c.upper() for c in sys.argv[1:]] if len(sys.argv) > 1 else sorted(by_team.keys())
    print(f"Generating {len(targets)} card(s)...")
    ok = 0
    for code in targets:
        if gen_one(code, by_team):
            ok += 1
    print(f"\n📦 Done: {ok}/{len(targets)} cards → {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
