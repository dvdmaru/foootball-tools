#!/usr/bin/env python3
"""分組總覽海報 PNG（FB/IG 分享用，1080×1350 4:5）。

#1 的 cross-channel artifact：頁面走 HTML（/standings/，SEO/GEO），
這張 PNG 給社群單圖分享。內容 = 12 組 × 4 隊國旗+中文名 + 關鍵日期。
品牌 @foootball 綠 #0d2818 / 金 #d4af37。

輸出：public/standings/schedule-poster.png（hotlinkable）。
"""

import json
import pathlib
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def chrome():
    for c in CHROME_CANDIDATES:
        if pathlib.Path(c).exists():
            return c
    raise SystemExit("Chrome not found")


def build_html():
    fd = json.loads((PUBLIC / "fixtures-data.json").read_text(encoding="utf-8"))
    teams = fd["teams"]
    groups = {}
    for t in teams:
        groups.setdefault(t["group"], []).append(t)

    cards = []
    for g in sorted(groups):
        rows = "".join(
            f'<div class="t">'
            f'<img src="https://flagcdn.com/w160/{t["iso"]}.png" alt="">'
            f'<span>{t["name_zh"]}</span></div>'
            for t in groups[g]
        )
        cards.append(f'<div class="card"><div class="g">{g}</div>{rows}</div>')
    cards_html = "".join(cards)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Noto+Sans+TC:wght@500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ width:1080px; height:1350px; background:
  radial-gradient(120% 70% at 50% -10%, #15402a 0%, transparent 55%), #0d2818;
  font-family:'Noto Sans TC',sans-serif; color:#fff; padding:54px 60px 40px;
  display:flex; flex-direction:column; }}
.head {{ text-align:center; margin-bottom:26px; }}
.kick {{ font-family:'Anton'; font-size:21px; letter-spacing:6px; color:#d4af37; margin-bottom:7px; }}
.title {{ font-family:'Anton'; font-size:70px; line-height:0.98; letter-spacing:1px; }}
.title b {{ color:#d4af37; }}
.sub {{ font-size:18px; color:#b8c9bb; margin-top:11px; letter-spacing:1px; }}
.grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }}
.card {{ background:rgba(255,255,255,0.045); border:1px solid rgba(212,175,55,0.28);
  border-radius:18px; padding:16px 16px 12px; }}
.g {{ font-family:'Anton'; font-size:38px; color:#d4af37; line-height:1; margin-bottom:10px;
  border-bottom:1px solid rgba(212,175,55,0.25); padding-bottom:7px; }}
.t {{ display:flex; align-items:center; gap:10px; padding:5px 0; }}
.t img {{ width:36px; height:24px; object-fit:cover; border-radius:3px;
  box-shadow:0 0 0 1px rgba(255,255,255,0.15); flex-shrink:0; }}
.t span {{ font-size:20px; font-weight:700; }}
.foot {{ margin-top:auto; padding-top:24px; text-align:center; }}
.foot .d {{ font-size:19px; color:#d4af37; font-weight:900; letter-spacing:1px; margin-bottom:6px; }}
.foot .u {{ font-family:'Anton'; font-size:24px; letter-spacing:3px; color:#fff; }}
</style></head><body>
<div class="head">
  <div class="kick">FIFA WORLD CUP 2026 · 美加墨</div>
  <div class="title">2026 世界盃<b>分組</b></div>
  <div class="sub">48 隊 · 12 組 · 6/11 開踢 · 完整賽程訂閱見下方</div>
</div>
<div class="grid">{cards_html}</div>
<div class="foot">
  <div class="d">📅 訂閱你的球隊賽程，自動同步行事曆</div>
  <div class="u">foootball.twtools.cc</div>
</div>
</body></html>"""


def main():
    html = build_html()
    out = PUBLIC / "standings" / "schedule-poster.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    subprocess.run(
        [chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=2", "--window-size=1080,1350",
         "--virtual-time-budget=5000",
         f"--screenshot={out}", f"file://{tmp}"],
        check=True, capture_output=True,
    )
    pathlib.Path(tmp).unlink(missing_ok=True)
    print(f"✅ {out}  ({out.stat().st_size // 1024} KB, 2160×2700 @2x)")


if __name__ == "__main__":
    main()
