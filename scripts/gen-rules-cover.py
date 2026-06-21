#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-rules-cover.py — @foootball evergreen 規則解說文封面生成器
HTML template → Chrome headless → 2400×1260 PNG（純文字、IP 安全：無 logo/球員照/隊徽）。
品牌：森林綠 #0d2818 + 金 #d4af37 / 亮金 #f0c850。
用法：python3 gen-rules-cover.py            # 生成全部
"""
import os, subprocess, tempfile, sys

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]

def chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("Chrome not found")

# (out_path, kicker, title_html, subtitle)
COVERS = [
    ("world-cup-2026-format",        "賽制 · FORMAT",     "2026 世界盃<br>賽制全解",   "48 隊　·　12 組　·　32 強淘汰賽"),
    ("world-cup-points-tiebreakers", "積分 · POINTS",     "積分與<br>晉級規則",       "勝3平1　·　同分排序　·　最佳第三名"),
    ("knockout-extra-time-penalties","淘汰賽 · KNOCKOUT", "延長賽與<br>點球大戰",     "30 分鐘延長　·　ABAB　·　驟死"),
    ("var-explained",                "VAR",               "VAR<br>完整指南",         "只管四件事　·　清楚而明顯的錯誤"),
    ("offside-rule-explained",       "越位 · OFFSIDE",    "越位規則<br>圖解",         "越位位置　·　介入比賽　·　折射"),
]

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{
  font-family:"PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  background:
    radial-gradient(1100px 700px at 78% -10%, rgba(212,175,55,.18), transparent 60%),
    linear-gradient(135deg,#0d2818 0%,#0a2014 55%,#071810 100%);
  color:#f0eee6;position:relative;
}}
.frame{{position:absolute;inset:28px;border:1.5px solid rgba(212,175,55,.38);border-radius:10px}}
.pad{{position:absolute;inset:0;padding:74px 78px;display:flex;flex-direction:column;height:100%}}
.top{{display:flex;align-items:center;gap:18px}}
.mark{{font-family:"Arial Black","PingFang TC",sans-serif;font-weight:900;letter-spacing:1px;
  font-size:30px;color:#f0c850}}
.dot{{width:7px;height:7px;border-radius:50%;background:#d4af37;opacity:.8}}
.mk-tag{{font-size:18px;color:rgba(240,238,230,.6);letter-spacing:2px;font-weight:600}}
.kicker{{margin-top:auto;display:inline-block;align-self:flex-start;
  background:rgba(212,175,55,.16);border:1px solid rgba(212,175,55,.5);
  color:#f0c850;font-size:24px;font-weight:700;letter-spacing:3px;
  padding:9px 22px;border-radius:999px}}
h1{{font-size:104px;line-height:1.08;font-weight:900;margin:26px 0 0;
  letter-spacing:1px;color:#fff;text-shadow:0 2px 30px rgba(0,0,0,.35)}}
.bar{{width:96px;height:5px;background:linear-gradient(90deg,#f0c850,#d4af37);
  border-radius:4px;margin:30px 0 22px}}
.sub{{font-size:33px;font-weight:600;color:rgba(240,238,230,.82);letter-spacing:1px}}
.foot{{position:absolute;left:78px;bottom:60px;font-size:21px;letter-spacing:2px;
  color:rgba(212,175,55,.72);font-weight:600}}
</style></head><body>
<div class="frame"></div>
<div class="pad">
  <div class="top"><span class="mark">@FOOOTBALL</span><span class="dot"></span>
    <span class="mk-tag">2026 WORLD CUP · 規則速查</span></div>
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="bar"></div>
  <div class="sub">{sub}</div>
</div>
<div class="foot">foootball.twtools.cc</div>
</body></html>"""

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.join(here, "covers-out")
    os.makedirs(outdir, exist_ok=True)
    for slug, kicker, title, sub in COVERS:
        html = HTML.format(kicker=kicker, title=title, sub=sub)
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html); tmp = f.name
        out = os.path.join(outdir, f"{slug}.png")
        subprocess.run(
            [chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
             "--force-device-scale-factor=2", "--window-size=1200,630",
             "--default-background-color=00000000",
             f"--screenshot={out}", f"file://{tmp}"],
            check=True, capture_output=True)
        os.unlink(tmp)
        print(f"✓ {out}")

if __name__ == "__main__":
    main()
