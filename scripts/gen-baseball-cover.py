#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-baseball-cover.py — @baseball 特刊封面生成器（baseball.twtools.cc）
HTML template → Chrome headless → 2400×1260 PNG（純文字、IP 安全：無 logo/球員照/隊徽/聯盟標誌）。
品牌：球場深藍 #0a1f3c + 米白 #f3efe4 + 暖金 #e8b84b（與 foootball 森林綠區隔）。
封面寫進 articles/<slug>/cover.png。

用法：python3 gen-baseball-cover.py            # 生成 COVERS 內全部
"""
import os, subprocess, tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("Chrome not found")


# (article_slug, kicker, title_html, subtitle)
COVERS = [
    ("mlb-special-ohtani-2024-50-50", "50-50 · 史上第一",
     "投不了球的<br>那一年",
     "大谷翔平 2024　·　54 轟　59 盜　·　全票 MVP"),
    ("mlb-ohtani-2026-two-way", "二刀流 · 完全體",
     "投手大谷<br>回來了",
     "2026　·　8 勝 2 敗　·　防禦率 1.58　·　86 K"),
    ("mlb-white-sox-2026-turnaround", "從谷底翻身",
     "41–121<br>之後",
     "白襪 2024 史上最慘　→　2026 領跑分區"),
    ("mlb-2026-midseason-report", "球季過半",
     "2026<br>戰況總覽",
     "六分區領先　·　全壘打榜　·　防禦率榜"),
]

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0;padding:0;box-sizing:border-box}}
html,body{{width:1200px;height:630px;overflow:hidden}}
body{{
  font-family:"PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  background:
    radial-gradient(1100px 720px at 80% -12%, rgba(232,184,75,.20), transparent 60%),
    linear-gradient(135deg,#0e2547 0%,#0a1f3c 52%,#061222 100%);
  color:#f3efe4;position:relative;
}}
.frame{{position:absolute;inset:28px;border:1.5px solid rgba(232,184,75,.40);border-radius:10px}}
.stitch{{position:absolute;left:0;right:0;top:50%;height:0;
  border-top:2px dashed rgba(200,71,47,.5);transform:rotate(-7deg) translateY(150px);opacity:.5}}
.pad{{position:absolute;inset:0;padding:74px 78px;display:flex;flex-direction:column;height:100%}}
.top{{display:flex;align-items:center;gap:18px}}
.mark{{font-family:"Arial Black","PingFang TC",sans-serif;font-weight:900;letter-spacing:1px;
  font-size:30px;color:#e8b84b}}
.dot{{width:7px;height:7px;border-radius:50%;background:#c8472f;opacity:.9}}
.mk-tag{{font-size:18px;color:rgba(243,239,228,.62);letter-spacing:2px;font-weight:600}}
.kicker{{margin-top:auto;display:inline-block;align-self:flex-start;
  background:rgba(232,184,75,.16);border:1px solid rgba(232,184,75,.52);
  color:#e8b84b;font-size:24px;font-weight:700;letter-spacing:3px;
  padding:9px 22px;border-radius:999px}}
h1{{font-size:104px;line-height:1.08;font-weight:900;margin:26px 0 0;
  letter-spacing:1px;color:#fff;text-shadow:0 2px 30px rgba(0,0,0,.40)}}
.bar{{width:96px;height:5px;background:linear-gradient(90deg,#e8b84b,#c8472f);
  border-radius:4px;margin:30px 0 22px}}
.sub{{font-size:32px;font-weight:600;color:rgba(243,239,228,.84);letter-spacing:1px}}
.foot{{position:absolute;left:78px;bottom:60px;font-size:21px;letter-spacing:2px;
  color:rgba(232,184,75,.74);font-weight:600}}
</style></head><body>
<div class="stitch"></div>
<div class="frame"></div>
<div class="pad">
  <div class="top"><span class="mark">@BASEBALL</span><span class="dot"></span>
    <span class="mk-tag">MLB 特刊 · 數據深度</span></div>
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="bar"></div>
  <div class="sub">{sub}</div>
</div>
<div class="foot">baseball.twtools.cc</div>
</body></html>"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    for slug, kicker, title, sub in COVERS:
        html = HTML.format(kicker=kicker, title=title, sub=sub)
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
            f.write(html); tmp = f.name
        art_dir = os.path.join(root, "articles", slug)
        os.makedirs(art_dir, exist_ok=True)
        out = os.path.join(art_dir, "cover.png")
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
