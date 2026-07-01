#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-baseball-brand-assets.py — @baseball 站台品牌資產（baseball.twtools.cc 根目錄）

產出（皆寫進 public-baseball/）：
  - og-home.png        2400×1260  首頁/文章列表頁 og:image（補 Meta 標籤分數）
  - apple-touch-icon.png  180×180  iOS 加入主畫面
  - icon-192.png / icon-512.png    PWA manifest 圖示
  - favicon.png        32×32       瀏覽器分頁圖示
  - site.webmanifest               PWA manifest（theme/icons）

全部純文字／幾何，IP 安全（無 logo/球員照/隊徽/聯盟標誌）。
品牌：球場深藍 #0a1f3c + 米白 #f3efe4 + 暖金 #e8b84b（與 foootball 森林綠區隔）。
icon 在 512 一次 render，PIL 高品質縮到 192/180/32（保持邊緣銳利）。

用法：python3 scripts/gen-baseball-brand-assets.py
"""
import os
import subprocess
import tempfile

from PIL import Image

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("Chrome not found")


def shot(html: str, out: str, w: int, h: int, scale: int = 2):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    subprocess.run(
        [chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
         f"--force-device-scale-factor={scale}", f"--window-size={w},{h}",
         "--default-background-color=00000000",
         f"--screenshot={out}", f"file://{tmp}"],
        check=True, capture_output=True)
    os.unlink(tmp)
    print(f"✓ {out}")


# ---------- og-home.png (2400×1260, render 1200×630 @2x) ----------
OG_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:1200px;height:630px;overflow:hidden}
body{font-family:"PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  background:radial-gradient(1100px 720px at 80% -12%, rgba(232,184,75,.20), transparent 60%),
    linear-gradient(135deg,#0e2547 0%,#0a1f3c 52%,#061222 100%);
  color:#f3efe4;position:relative}
.frame{position:absolute;inset:28px;border:1.5px solid rgba(232,184,75,.40);border-radius:10px}
.stitch{position:absolute;left:0;right:0;top:50%;height:0;
  border-top:2px dashed rgba(200,71,47,.5);transform:rotate(-7deg) translateY(150px);opacity:.5}
.pad{position:absolute;inset:0;padding:78px 82px;display:flex;flex-direction:column;height:100%}
.top{display:flex;align-items:center;gap:18px}
.mark{font-family:"Arial Black","PingFang TC",sans-serif;font-weight:900;letter-spacing:1px;
  font-size:32px;color:#e8b84b}
.dot{width:7px;height:7px;border-radius:50%;background:#c8472f;opacity:.9}
.mk-tag{font-size:18px;color:rgba(243,239,228,.62);letter-spacing:2px;font-weight:600}
h1{font-size:96px;line-height:1.1;font-weight:900;margin:auto 0 0;letter-spacing:1px;
  color:#fff;text-shadow:0 2px 30px rgba(0,0,0,.40)}
.bar{width:96px;height:5px;background:linear-gradient(90deg,#e8b84b,#c8472f);
  border-radius:4px;margin:28px 0 22px}
.sub{font-size:30px;font-weight:600;color:rgba(243,239,228,.84);letter-spacing:1px}
.foot{position:absolute;left:82px;bottom:62px;font-size:21px;letter-spacing:2px;
  color:rgba(232,184,75,.74);font-weight:600}
</style></head><body>
<div class="stitch"></div><div class="frame"></div>
<div class="pad">
  <div class="top"><span class="mark">@BASEBALL</span><span class="dot"></span>
    <span class="mk-tag">中職 CPBL + 大聯盟 MLB · 數據深度</span></div>
  <h1>看門道的棒球，<br>用數據說話。</h1>
  <div class="bar"></div>
  <div class="sub">戰績排行 · 主客場拆分 · 球員名冊 · 里程碑特刊　|　繁體中文 · 台北時間</div>
</div>
<div class="foot">baseball.twtools.cc</div>
</body></html>"""


# ---------- icon (render 512×512 @1x, PIL downscale) ----------
ICON_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:512px;height:512px;overflow:hidden}
body{font-family:"Arial Black","PingFang TC",sans-serif;
  background:radial-gradient(360px 360px at 70% 18%, rgba(232,184,75,.28), transparent 62%),
    linear-gradient(135deg,#0e2547 0%,#0a1f3c 55%,#061222 100%);
  position:relative;display:flex;align-items:center;justify-content:center}
.ring{position:absolute;inset:44px;border:6px solid rgba(232,184,75,.55);border-radius:50%}
.stitch{position:absolute;left:50%;top:74px;bottom:74px;width:0;
  border-left:5px dashed rgba(200,71,47,.8);transform:rotate(20deg)}
.b{font-size:300px;font-weight:900;color:#e8b84b;line-height:1;
  text-shadow:0 6px 30px rgba(0,0,0,.45);position:relative;margin-top:-8px}
</style></head><body>
<div class="ring"></div><div class="stitch"></div>
<div class="b">B</div>
</body></html>"""

MANIFEST = """{
  "name": "@baseball — 中職 CPBL + 大聯盟 MLB 數據深度",
  "short_name": "@baseball",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0a1f3c",
  "theme_color": "#0a1f3c",
  "icons": [
    { "src": "/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ]
}
"""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    pub = os.path.join(root, "public-baseball")
    os.makedirs(pub, exist_ok=True)

    # og-home: 1200×630 @2x = 2400×1260
    shot(OG_HTML, os.path.join(pub, "og-home.png"), 1200, 630, scale=2)

    # icon master at 512, then PIL downscale (high quality)
    master = os.path.join(pub, "icon-512.png")
    shot(ICON_HTML, master, 512, 512, scale=1)
    img = Image.open(master).convert("RGBA")
    if img.size != (512, 512):
        img = img.resize((512, 512), Image.LANCZOS)
        img.save(master)
    for size, name in [(192, "icon-192.png"), (180, "apple-touch-icon.png"), (32, "favicon.png")]:
        img.resize((size, size), Image.LANCZOS).save(os.path.join(pub, name))
        print(f"✓ {os.path.join(pub, name)}")

    with open(os.path.join(pub, "site.webmanifest"), "w", encoding="utf-8") as f:
        f.write(MANIFEST)
    print(f"✓ {os.path.join(pub, 'site.webmanifest')}")


if __name__ == "__main__":
    main()
