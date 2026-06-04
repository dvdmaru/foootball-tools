#!/usr/bin/env python3
"""
build-articles.py — markdown → static HTML + 套 design tokens (同 public/index.html 7 主題)

Input:
    articles/<slug>/index.md + assets (cover.png, table-*.png, etc)

Output:
    public/articles/<slug>/index.html + cp assets
    public/articles/index.html  (article 列表，sorted by date desc)

Frontmatter (per article):
    ---
    slug: <slug>
    type: daily | feature
    date: YYYY-MM-DD
    title: "..."
    subtitle: "..."
    vol: N (daily only)
    ---

用法：
    python3 scripts/build-articles.py
"""

import pathlib
import re
import shutil
import sys
import datetime
import html as html_lib

import markdown as md_lib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "articles"
OUT = ROOT / "public" / "articles"

WEEKDAY_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


# ---------- shared design tokens (與 public/index.html 同步) ----------

SHARED_TOKENS_CSS = """
:root {
  --radius: 16px;
  --radius-sm: 11px;
  --font-display: 'Anton', 'Noto Sans TC', sans-serif;
  --font-ui: 'Archivo', 'Noto Sans TC', -apple-system, BlinkMacSystemFont, 'PingFang TC', 'Microsoft JhengHei', sans-serif;
  --font-mono: ui-monospace, 'SF Mono', 'Cascadia Mono', Menlo, monospace;
  --surface: #ffffff; --surface-2: #f8faf6; --surface-3: #eef1ec;
  --fg: #1b211e; --fg-soft: #49534d; --dim: #6f7a73; --faint: #9aa39d;
  --line: rgba(20,28,24,0.10); --line-2: rgba(20,28,24,0.17);
  --sheet-shadow: rgba(20,28,24,0.16); --scrim: rgba(20,28,24,0.34);
}
:root[data-theme="grass"]    { --bg:#f1f4ed; --bg-glow:#e2efdc; --accent:#1f9d63; --accent-bright:#23b372; --accent-ink:#ffffff; --accent-soft:rgba(31,157,99,0.10);  --accent-line:rgba(31,157,99,0.30);  --accent-glow:rgba(31,157,99,0.26); }
:root[data-theme="cobalt"]   { --bg:#eef1f7; --bg-glow:#e1e8f7; --accent:#2b5ce0; --accent-bright:#3a6bf0; --accent-ink:#ffffff; --accent-soft:rgba(43,92,224,0.10);  --accent-line:rgba(43,92,224,0.30);  --accent-glow:rgba(43,92,224,0.26); }
:root[data-theme="tangerine"]{ --bg:#f7f1e9; --bg-glow:#f3e6d4; --accent:#d4622a; --accent-bright:#e8743a; --accent-ink:#ffffff; --accent-soft:rgba(212,98,42,0.10);  --accent-line:rgba(212,98,42,0.30);  --accent-glow:rgba(212,98,42,0.26); }
:root[data-theme="berry"]    { --bg:#f6eef2; --bg-glow:#f2e1ea; --accent:#c0356f; --accent-bright:#d44a82; --accent-ink:#ffffff; --accent-soft:rgba(192,53,111,0.10); --accent-line:rgba(192,53,111,0.30); --accent-glow:rgba(192,53,111,0.26); }
:root[data-theme="teal"]     { --bg:#ebf2f1; --bg-glow:#dcecea; --accent:#0f8a8a; --accent-bright:#14a3a0; --accent-ink:#ffffff; --accent-soft:rgba(15,138,138,0.10); --accent-line:rgba(15,138,138,0.30); --accent-glow:rgba(15,138,138,0.26); }
:root[data-theme="plum"]     { --bg:#f1eef6; --bg-glow:#e6e1f3; --accent:#6c4bd1; --accent-bright:#7d5ee0; --accent-ink:#ffffff; --accent-soft:rgba(108,75,209,0.10); --accent-line:rgba(108,75,209,0.30); --accent-glow:rgba(108,75,209,0.26); }
:root[data-theme="dark"] {
  --surface: #143524; --surface-2: #1a4530; --surface-3: #1f4a36;
  --fg: #e8f0e6; --fg-soft: #b8c5bb; --dim: #8a9c8d; --faint: #6a7a6e;
  --line: rgba(232,240,230,0.10); --line-2: rgba(232,240,230,0.18);
  --sheet-shadow: rgba(0,0,0,0.55); --scrim: rgba(0,0,0,0.55);
  --bg: #0d2818; --bg-glow: #143a26; --accent: #d4af37; --accent-bright: #f0c850;
  --accent-ink: #0d2818; --accent-soft: rgba(212,175,55,0.12); --accent-line: rgba(212,175,55,0.35); --accent-glow: rgba(212,175,55,0.30);
}
:root[data-theme="dark"] body::before { mix-blend-mode: screen; opacity: 0.22; }
:root[data-theme="dark"] .theme-switch { box-shadow: 0 6px 22px rgba(0,0,0,0.45); }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: var(--bg); color: var(--fg); font-family: var(--font-ui);
  line-height: 1.6; -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
body {
  min-height: 100vh; padding: 0 16px 110px; position: relative;
  background: radial-gradient(130% 72% at 50% -12%, var(--bg-glow) 0%, transparent 56%), var(--bg);
}
body::before {
  content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 0; opacity: 0.4;
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.05'/%3E%3C/svg%3E");
}
"""

THEME_SWITCH_CSS = """
.theme-switch {
  position: fixed; top: 14px; right: 16px; z-index: 150;
  display: flex; align-items: center; gap: 11px;
  background: color-mix(in srgb, var(--surface) 86%, transparent);
  border: 1px solid var(--line); border-radius: 99px;
  padding: 7px 13px 7px 14px; box-shadow: 0 6px 22px rgba(20,28,24,0.10);
  backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
}
.ts-label { font-family: var(--font-mono); font-size: 10px; letter-spacing: 1.5px; color: var(--dim); text-transform: uppercase; }
.ts-dots { display: flex; gap: 8px; }
.ts-dot {
  width: 19px; height: 19px; border-radius: 50%; padding: 0; cursor: pointer;
  background: var(--sw); border: 2px solid var(--surface);
  box-shadow: 0 0 0 1px var(--line-2);
  transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.ts-dot:hover { transform: scale(1.14); }
.ts-dot.active { box-shadow: 0 0 0 2px var(--sw); transform: scale(1.05); }
@media (max-width: 520px) {
  .theme-switch { top: 10px; right: 10px; padding: 6px 11px; gap: 9px; }
  .ts-label { display: none; }
}
"""

THEME_SWITCH_HTML = """
<div class="theme-switch">
  <span class="ts-label">配色</span>
  <div class="ts-dots">
    <button class="ts-dot" data-theme="grass" onclick="setTheme('grass')" style="--sw:#1f9d63" aria-label="草綠"></button>
    <button class="ts-dot" data-theme="cobalt" onclick="setTheme('cobalt')" style="--sw:#2b5ce0" aria-label="鈷藍"></button>
    <button class="ts-dot" data-theme="tangerine" onclick="setTheme('tangerine')" style="--sw:#d4622a" aria-label="暖橘"></button>
    <button class="ts-dot" data-theme="berry" onclick="setTheme('berry')" style="--sw:#c0356f" aria-label="莓紅"></button>
    <button class="ts-dot" data-theme="teal" onclick="setTheme('teal')" style="--sw:#0f8a8a" aria-label="湖青"></button>
    <button class="ts-dot" data-theme="plum" onclick="setTheme('plum')" style="--sw:#6c4bd1" aria-label="紫"></button>
    <button class="ts-dot" data-theme="dark" onclick="setTheme('dark')" style="--sw:#0d2818" aria-label="深綠（brand）"></button>
  </div>
</div>
"""

THEME_SWITCH_JS = """
const THEMES = ['grass','cobalt','tangerine','berry','teal','plum','dark'];
function setTheme(t) {
  if (!THEMES.includes(t)) t = 'grass';
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('wc-theme', t); } catch (e) {}
  document.querySelectorAll('.ts-dot').forEach(d => d.classList.toggle('active', d.dataset.theme === t));
}
(function initTheme() {
  let t = 'grass';
  try { t = localStorage.getItem('wc-theme') || 'grass'; } catch (e) {}
  setTheme(t);
})();
"""


# ---------- article page CSS ----------

ARTICLE_CSS = """
.container { max-width: 720px; margin: 0 auto; position: relative; z-index: 1; padding-top: 60px; }
.nav-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; font-family: var(--font-mono); font-size: 12px; letter-spacing: 1.5px; }
.nav-row a { color: var(--dim); text-decoration: none; transition: color 0.15s ease; }
.nav-row a:hover { color: var(--accent); }
.nav-row .brand { color: var(--fg); font-weight: 700; letter-spacing: 0.5px; }

.article-header { margin-bottom: 32px; padding-bottom: 26px; border-bottom: 1px solid var(--line); }
.article-kicker {
  display: inline-flex; align-items: center; gap: 10px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px;
  text-transform: uppercase; color: var(--accent); margin-bottom: 18px; font-weight: 600;
}
.article-kicker::before { content: ''; width: 22px; height: 2px; background: var(--accent); }
.article-title { font-family: var(--font-display); font-weight: 400; font-size: clamp(30px, 5.5vw, 46px); line-height: 1.15; color: var(--fg); margin-bottom: 14px; letter-spacing: 0.3px; }
.article-title .tc { font-family: var(--font-ui); font-weight: 900; letter-spacing: -0.3px; }
.article-subtitle { font-size: 17px; color: var(--fg-soft); line-height: 1.55; font-weight: 500; }
.article-meta { font-family: var(--font-mono); font-size: 12px; color: var(--dim); margin-top: 16px; letter-spacing: 1px; }
.article-meta .dot { display: inline-block; width: 4px; height: 4px; border-radius: 50%; background: var(--faint); vertical-align: middle; margin: 0 9px 2px; }

.article-cover { width: 100%; max-width: 100%; height: auto; border-radius: var(--radius-sm); margin: 0 0 36px; box-shadow: 0 10px 30px var(--sheet-shadow); }

.prose { color: var(--fg-soft); font-size: 16.5px; line-height: 1.85; }
.prose h2 { font-family: var(--font-display); font-weight: 400; font-size: 28px; line-height: 1.2; color: var(--fg); margin: 48px 0 18px; letter-spacing: 0.3px; }
.prose h3 { font-size: 21px; font-weight: 700; color: var(--fg); margin: 36px 0 14px; line-height: 1.35; }
.prose h4 { font-size: 17.5px; font-weight: 700; color: var(--fg); margin: 28px 0 12px; }
.prose p { margin: 0 0 18px; }
.prose strong { color: var(--fg); font-weight: 700; }
.prose em { font-style: italic; }
.prose a { color: var(--accent); text-decoration: none; border-bottom: 1px solid var(--accent-line); transition: border-color 0.15s ease; }
.prose a:hover { border-bottom-color: var(--accent); }
.prose img { display: block; width: 100%; height: auto; max-width: 100%; border-radius: var(--radius-sm); margin: 30px 0; box-shadow: 0 6px 22px var(--sheet-shadow); }
.prose blockquote { border-left: 3px solid var(--accent); background: var(--surface-2); padding: 14px 20px; margin: 24px 0; border-radius: 0 var(--radius-sm) var(--radius-sm) 0; color: var(--fg); font-style: normal; }
.prose blockquote p { margin: 0 0 8px; }
.prose blockquote p:last-child { margin: 0; }
.prose ul, .prose ol { padding-left: 24px; margin: 0 0 22px; }
.prose li { margin: 0 0 8px; }
.prose hr { border: none; height: 1px; background: var(--line); margin: 40px 0; }
.prose code { background: var(--surface-3); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono); font-size: 0.92em; color: var(--fg); }
.prose pre { background: var(--surface-3); padding: 14px 16px; border-radius: var(--radius-sm); overflow-x: auto; margin: 20px 0; }
.prose pre code { background: transparent; padding: 0; }

.article-footer { margin-top: 60px; padding-top: 28px; border-top: 1px solid var(--line); display: flex; flex-direction: column; align-items: center; gap: 22px; }
.cta-btn {
  display: inline-flex; align-items: center; gap: 9px;
  padding: 16px 28px; border-radius: 13px;
  background-color: var(--accent); color: var(--accent-ink);
  text-decoration: none; font-weight: 800; font-size: 15px; letter-spacing: 0.4px;
  box-shadow: 0 10px 26px var(--accent-glow);
  transition: transform 0.18s cubic-bezier(0.22,1,0.36,1), background-color 0.18s ease;
}
.cta-btn:hover { transform: translateY(-2px); background-color: var(--accent-bright); }
.foot-links { display: flex; gap: 22px; font-family: var(--font-mono); font-size: 12.5px; letter-spacing: 1px; }
.foot-links a { color: var(--dim); text-decoration: none; }
.foot-links a:hover { color: var(--accent); }
"""


# ---------- index page CSS ----------

INDEX_CSS = """
.container { max-width: 900px; margin: 0 auto; position: relative; z-index: 1; padding-top: 56px; }
.idx-header { margin-bottom: 44px; padding-bottom: 26px; border-bottom: 1px solid var(--line); }
.idx-kicker { display: flex; align-items: center; gap: 12px; font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 3px; text-transform: uppercase; color: var(--dim); margin-bottom: 18px; }
.idx-kicker::before { content: ''; width: 26px; height: 2px; background: var(--accent); }
.idx-kicker b { color: var(--accent); font-weight: 600; }
.idx-h1 { font-family: var(--font-display); font-weight: 400; font-size: clamp(40px, 7.5vw, 70px); line-height: 0.95; color: var(--fg); letter-spacing: 0.5px; }
.idx-h1 .tc { font-family: var(--font-ui); font-weight: 900; letter-spacing: -0.5px; }
.idx-sub { margin-top: 18px; font-size: 14.5px; color: var(--fg-soft); }
.idx-sub a { color: var(--accent); text-decoration: none; font-weight: 600; }

.idx-list { display: flex; flex-direction: column; gap: 22px; }
.idx-card {
  display: grid; grid-template-columns: 200px 1fr; gap: 26px; align-items: stretch;
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 18px;
  text-decoration: none; color: inherit;
  transition: transform 0.22s cubic-bezier(0.22,1,0.36,1), border-color 0.2s ease, box-shadow 0.2s ease;
}
.idx-card:hover { transform: translateY(-3px); border-color: var(--line-2); box-shadow: 0 14px 34px var(--sheet-shadow); }
.idx-cover { width: 100%; height: 130px; object-fit: cover; border-radius: var(--radius-sm); display: block; }
.idx-body { display: flex; flex-direction: column; padding: 4px 0; }
.idx-card-kicker { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 2.5px; text-transform: uppercase; color: var(--accent); font-weight: 700; margin-bottom: 9px; }
.idx-card-title { font-size: 18.5px; font-weight: 700; color: var(--fg); line-height: 1.35; margin-bottom: 7px; }
.idx-card-sub { font-size: 14px; color: var(--fg-soft); line-height: 1.55; margin-bottom: 10px; flex: 1; }
.idx-card-meta { font-family: var(--font-mono); font-size: 11.5px; color: var(--dim); letter-spacing: 1px; }
@media (max-width: 640px) {
  .idx-card { grid-template-columns: 1fr; gap: 14px; padding: 14px; }
  .idx-cover { height: 180px; }
}
"""


# ---------- frontmatter parser ----------

def parse_frontmatter(text: str):
    """Split YAML-ish frontmatter from markdown body. Returns (meta dict, body str)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    fm = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    meta = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        elif v.isdigit():
            v = int(v)
        meta[k.strip()] = v
    return meta, body


# ---------- markdown body preprocess ----------

def strip_medium_guide(body: str) -> str:
    """Strip the daily-only "Medium 貼稿指南" blockquote section + its trailing ---."""
    pattern = re.compile(r"> \*\*Medium 貼稿指南\*\*.*?(?:\n---\n)", re.DOTALL)
    return pattern.sub("", body, count=1)


def inject_inline_images(body: str) -> str:
    """[📸 插入 PNG: filename] -> ![](filename)"""
    return re.sub(r"\[📸 插入 PNG: ([^\]]+?)\]", r"![](\1)", body)


def strip_h1(body: str) -> str:
    """Drop the first H1 (we render title via the article header)."""
    return re.sub(r"^# .*\n", "", body, count=1).lstrip("\n")


# ---------- render ----------

def render_article(meta: dict, body_html: str, slug: str) -> str:
    typ = meta.get("type", "feature")
    if typ == "daily":
        vol = meta.get("vol", "?")
        kicker = f"DAILY · VOL. {int(vol):03d}" if isinstance(vol, int) else f"DAILY · VOL. {vol}"
    else:
        kicker = "FEATURE"
    title_raw = meta.get("title", slug)
    title_safe = html_lib.escape(title_raw)
    subtitle = html_lib.escape(meta.get("subtitle", ""))
    date_str = str(meta.get("date", ""))
    try:
        d = datetime.date.fromisoformat(date_str)
        date_disp = f"{d.year}/{d.month:02d}/{d.day:02d} · {WEEKDAY_ZH[d.weekday()]}"
    except Exception:
        date_disp = date_str

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="grass">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title_safe} | @foootball</title>
<meta name="description" content="{subtitle}">
<meta property="og:title" content="{title_safe}">
<meta property="og:description" content="{subtitle}">
<meta property="og:image" content="https://foootball.twtools.cc/articles/{slug}/cover.png">
<meta property="og:type" content="article">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{ARTICLE_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">
  <div class="nav-row">
    <a href="/articles/">← 文章列表</a>
    <a href="/" class="brand">@foootball · 賽程訂閱</a>
  </div>
  <article>
    <header class="article-header">
      <div class="article-kicker">{kicker}</div>
      <h1 class="article-title">{title_safe}</h1>
      <div class="article-subtitle">{subtitle}</div>
      <div class="article-meta">{date_disp}</div>
    </header>
    <img class="article-cover" src="cover.png" alt="">
    <div class="prose">
{body_html}
    </div>
  </article>
  <div class="article-footer">
    <a href="/" class="cta-btn">👉 訂閱你的球隊賽程</a>
    <div class="foot-links">
      <a href="/articles/">所有文章</a>
      <a href="https://medium.com/@foootball" target="_blank">Medium</a>
      <a href="/">賽程訂閱</a>
    </div>
  </div>
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


def render_index(articles: list) -> str:
    cards_html = ""
    for a in articles:
        typ = a["meta"].get("type", "feature")
        if typ == "daily":
            vol = a["meta"].get("vol", "?")
            kicker = f"DAILY · VOL. {int(vol):03d}" if isinstance(vol, int) else f"DAILY · VOL. {vol}"
        else:
            kicker = "FEATURE"
        title = html_lib.escape(a["meta"].get("title", a["slug"]))
        sub = html_lib.escape(a["meta"].get("subtitle", ""))
        date_str = str(a["meta"].get("date", ""))
        try:
            d = datetime.date.fromisoformat(date_str)
            date_disp = f"{d.year}/{d.month:02d}/{d.day:02d} · {WEEKDAY_ZH[d.weekday()]}"
        except Exception:
            date_disp = date_str
        cards_html += f"""
    <a class="idx-card" href="/articles/{a['slug']}/">
      <img class="idx-cover" src="/articles/{a['slug']}/cover.png" alt="">
      <div class="idx-body">
        <div class="idx-card-kicker">{kicker}</div>
        <div class="idx-card-title">{title}</div>
        <div class="idx-card-sub">{sub}</div>
        <div class="idx-card-meta">{date_disp}</div>
      </div>
    </a>"""

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="grass">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>文章 — 2026 世界盃每日戰報 + 焦點觀察 | @foootball</title>
<meta name="description" content="2026 世界盃每日戰報、焦點觀察、規則解讀。台北時間，繁體中文。">
<meta property="og:title" content="文章 — @foootball 世界盃">
<meta property="og:description" content="每日戰報、規則解讀、焦點觀察。">
<meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{INDEX_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">
  <div class="nav-row" style="margin-bottom: 40px;">
    <a href="/">← 賽程訂閱站</a>
    <a href="https://medium.com/@foootball" target="_blank" class="brand">Medium @foootball ↗</a>
  </div>
  <header class="idx-header">
    <div class="idx-kicker">@foootball · <b>文章</b></div>
    <h1 class="idx-h1"><span class="tc">2026 世界盃</span></h1>
    <div class="idx-sub">每日戰報 · 焦點觀察 · 規則解讀 — 全部繁體中文 / 台北時間</div>
  </header>
  <div class="idx-list">{cards_html}
  </div>
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


# ---------- main build ----------

def build():
    if not SRC.exists():
        print(f"❌ {SRC} not found", file=sys.stderr)
        sys.exit(1)

    articles = []
    for d in sorted(SRC.iterdir()):
        if not d.is_dir():
            continue
        md_path = d / "index.md"
        if not md_path.exists():
            continue
        text = md_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)
        meta.setdefault("slug", d.name)
        slug = meta["slug"]

        if meta.get("type") == "daily":
            body = strip_medium_guide(body)
        body = inject_inline_images(body)
        body = strip_h1(body)

        body_html = md_lib.markdown(body, extensions=["extra", "sane_lists"])

        out_dir = OUT / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        # cp all non-md assets
        for asset in d.iterdir():
            if asset.is_file() and asset.suffix != ".md":
                shutil.copy2(asset, out_dir / asset.name)

        (out_dir / "index.html").write_text(render_article(meta, body_html, slug), encoding="utf-8")
        articles.append({"slug": slug, "meta": meta})
        print(f"✅ {slug}")

    # index — sort by date desc
    articles_sorted = sorted(articles, key=lambda a: str(a["meta"].get("date", "")), reverse=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render_index(articles_sorted), encoding="utf-8")
    print(f"📚 index.html ({len(articles_sorted)} articles) → {OUT}/index.html")


if __name__ == "__main__":
    build()
