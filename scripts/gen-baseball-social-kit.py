#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-baseball-social-kit.py — 棒球數據誌 / @baseball 社群品牌包（baseball.twtools.cc）

HTML template → Chrome headless → PNG（純文字/幾何、IP 安全：無 logo/球員照/隊徽/聯盟標誌）。
品牌：navy #0a1f3c + gold #e8b84b + red #c8472f + cream #f3efe4（與 gen-baseball-cover.py 同色系）。

產出（寫進 scripts/social-out/baseball/）：
  avatar.png    1080×1080  方形頭像（Threads / IG / FB 共用）— 「@B」金色字標 monogram + 紅色棒球縫線
  fb-cover.png  1640×856   Facebook 粉專封面（顯示 820×312；左下留安全區給頭像）

用法：python3 gen-baseball-social-kit.py
"""
import os
import subprocess
import tempfile

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


def chrome():
    for c in CHROME_CANDIDATES:
        if os.path.exists(c):
            return c
    raise SystemExit("Chrome not found")


# ── Avatar 1080×1080（window 540×540 × scale 2）────────────────────────────
AVATAR_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:540px;height:540px;overflow:hidden}
body{
  font-family:"Arial Black","PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  background:
    radial-gradient(420px 420px at 50% 40%, rgba(232,184,75,.20), transparent 62%),
    linear-gradient(135deg,#0e2547 0%,#0a1f3c 55%,#061222 100%);
  color:#f3efe4;position:relative;
}
.frame{position:absolute;inset:22px;border:2px solid rgba(232,184,75,.42);border-radius:26px}
/* 棒球縫線：環繞 @B 的虛線圓，左右各補一道弧線做出棒球縫線感 */
.ball{position:absolute;left:50%;top:43%;width:362px;height:362px;
  transform:translate(-50%,-50%)}
.ring{position:absolute;inset:0;border-radius:50%;border:3px dashed rgba(200,71,47,.55)}
.seam{position:absolute;top:8%;height:84%;width:150px;border:3px dashed rgba(200,71,47,.5);
  border-radius:50%}
.seam.l{left:-34px;border-right:none;border-top:none;border-bottom:none}
.seam.r{right:-34px;border-left:none;border-top:none;border-bottom:none}
.mono{position:absolute;left:50%;top:43%;transform:translate(-50%,-50%);
  font-weight:900;color:#e8b84b;letter-spacing:-2px;line-height:1;
  text-shadow:0 4px 26px rgba(0,0,0,.45)}
.mono .at{font-size:128px;color:#f3c860;vertical-align:0.04em;margin-right:-6px}
.mono .b{font-size:228px}
.bar{position:absolute;left:50%;bottom:118px;transform:translateX(-50%);
  width:120px;height:6px;border-radius:4px;background:linear-gradient(90deg,#e8b84b,#c8472f)}
.name{position:absolute;left:0;right:0;bottom:64px;text-align:center;
  font-family:"PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  font-weight:700;font-size:42px;letter-spacing:10px;color:#f3efe4;
  text-indent:10px}
</style></head><body>
<div class="frame"></div>
<div class="ball">
  <div class="ring"></div>
  <div class="seam l"></div>
  <div class="seam r"></div>
</div>
<div class="mono"><span class="at">@</span><span class="b">B</span></div>
<div class="bar"></div>
<div class="name">棒球數據誌</div>
</body></html>"""


# ── Facebook cover 1640×856（window 820×428 × scale 2）─────────────────────
# FB 顯示區約 820×312，行動版會再裁切；左下角桌面版會疊頭像 → 關鍵字置中、footer 靠右。
FB_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{width:820px;height:428px;overflow:hidden}
body{
  font-family:"PingFang TC","Heiti TC","Noto Sans CJK TC",sans-serif;
  background:
    radial-gradient(900px 560px at 78% -16%, rgba(232,184,75,.20), transparent 60%),
    linear-gradient(135deg,#0e2547 0%,#0a1f3c 52%,#061222 100%);
  color:#f3efe4;position:relative;
}
.frame{position:absolute;inset:20px;border:1.5px solid rgba(232,184,75,.40);border-radius:14px}
.stitch{position:absolute;left:0;right:0;top:50%;height:0;
  border-top:2px dashed rgba(200,71,47,.45);transform:rotate(-6deg) translateY(120px);opacity:.55}
.wrap{position:absolute;inset:0;display:flex;flex-direction:column;
  align-items:center;justify-content:center;text-align:center;padding:0 60px 26px}
.mark{font-family:"Arial Black","PingFang TC",sans-serif;font-weight:900;
  font-size:30px;letter-spacing:1px;color:#e8b84b;display:flex;align-items:center;gap:13px}
.mark .dot{width:8px;height:8px;border-radius:50%;background:#c8472f;opacity:.9}
.mark .tag{font-family:"PingFang TC",sans-serif;font-size:17px;font-weight:600;
  letter-spacing:2px;color:rgba(243,239,228,.6)}
h1{font-size:68px;font-weight:900;letter-spacing:8px;color:#f3efe4;
  margin:18px 0 0;text-indent:8px;text-shadow:0 2px 24px rgba(0,0,0,.4)}
.bar{width:120px;height:5px;border-radius:4px;
  background:linear-gradient(90deg,#e8b84b,#c8472f);margin:22px 0 18px}
.line{font-size:25px;font-weight:600;letter-spacing:2px;color:rgba(243,239,228,.86)}
.foot{position:absolute;right:46px;bottom:34px;font-size:18px;letter-spacing:2px;
  font-weight:600;color:rgba(232,184,75,.78)}
</style></head><body>
<div class="stitch"></div>
<div class="frame"></div>
<div class="wrap">
  <div class="mark"><span>@BASEBALL</span><span class="dot"></span>
    <span class="tag">非官方數據整理站</span></div>
  <h1>棒球數據誌</h1>
  <div class="bar"></div>
  <div class="line">中職 CPBL × 大聯盟 MLB　·　數據深度</div>
</div>
<div class="foot">baseball.twtools.cc</div>
</body></html>"""


# (filename, html, window_w, window_h)
ASSETS = [
    ("avatar.png", AVATAR_HTML, 540, 540),
    ("fb-cover.png", FB_HTML, 820, 428),
]


def render(html, out, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name
    subprocess.run(
        [chrome(), "--headless", "--disable-gpu", "--hide-scrollbars",
         "--force-device-scale-factor=2", f"--window-size={w},{h}",
         "--default-background-color=00000000",
         f"--screenshot={out}", f"file://{tmp}"],
        check=True, capture_output=True)
    os.unlink(tmp)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "social-out", "baseball")
    os.makedirs(out_dir, exist_ok=True)
    for name, html, w, h in ASSETS:
        out = os.path.join(out_dir, name)
        render(html, out, w, h)
        print(f"✓ {out}  ({w*2}×{h*2})")


if __name__ == "__main__":
    main()
