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
    lede: "..."   # optional — 40–80 字直接答案（AEO 短答），render 成「重點速答」盒
                  #            + 餵進 meta description / Article.description
    ---

AEO FAQ（optional）：在 markdown body 末段寫一個 FAQ 區段，build 會自動產
FAQPage JSON-LD（可見內容照常 render，schema 文字＝可見文字）：

    ## 常見問題
    ### 問句一？
    答案段落一。
    ### 問句二？
    答案段落二。

接受的區段標題：`## 常見問題` / `## 常見問答` / `## FAQ`。
內容務必由人工／pipeline 依已驗事實撰寫，build 端不生成任何 FAQ 文字。

用法：
    python3 scripts/build-articles.py
"""

import pathlib
import re
import shutil
import sys
import datetime
import json
import html as html_lib

import markdown as md_lib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "articles"
OUT = ROOT / "public" / "articles"
SITE = "https://foootball.twtools.cc"
ORG_NAME = "@foootball"

WEEKDAY_ZH = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]


# ---------- competition registry (multi-competition single source of truth) ----------
# config/competitions.json drives schema.org nodes, cadence, data source and IA per
# competition. Phase 1 holds only wc2026; tournament_node() is now a thin alias over
# competition_node(wc2026) and emits byte-identical JSON-LD to the previous hardcode.
def load_competitions() -> dict:
    p = ROOT / "config" / "competitions.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


COMPETITIONS = load_competitions()


# ---------- per-sport site identity (multi-sport single source of truth) ----------
# config/sites.json carries org/website identity per sport (base URL, org name, sameAs,
# website name). A comp resolves its site via its `sport` field; comps without `sport`
# (every existing soccer comp) fall back to SOCCER_SITE, whose values equal the legacy
# SITE/ORG_NAME constants -> existing soccer pages emit byte-identical JSON-LD.
def load_sites() -> dict:
    p = ROOT / "config" / "sites.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


SITES = load_sites()

# Hardcoded fallback == legacy constants, so a missing/partial sites.json never changes
# the soccer output (the regression contract). sites.json["soccer"] must match this.
SOCCER_SITE = SITES.get("soccer") or {
    "base": SITE,
    "org_name": ORG_NAME,
    "org_same_as": ["https://medium.com/@foootball"],
    "website_name": "@foootball — 2026 世界盃賽程 + 戰報",
    "brand_mark": "@FOOOTBALL",
    "brand_tag": "2026 World Cup · 賽程 + 戰報",
    "title_suffix": "@foootball",
    "feed_title": "@foootball 最新文章",
    "feed_channel_title": "@foootball — 2026 世界盃戰報與專題",
    "feed_channel_desc": "2026 FIFA 世界盃每日戰報、規則解析與專題文章。",
    "default_theme": "grass",
    "nav": [
        {"label": "賽程訂閱", "href": "/", "key": "home"},
        {"label": "戰況", "href": "/standings/", "key": "standings"},
        {"label": "文章", "href": "/articles/", "key": "articles"},
    ],
    "external_link": {"label": "Medium ↗", "href": "https://medium.com/@foootball"},
    "footer_cta": {"label": "👉 訂閱你的球隊賽程", "href": "/"},
    "footer_links": [
        {"label": "所有文章", "href": "/articles/"},
        {"label": "Medium", "href": "https://medium.com/@foootball", "external": True},
        {"label": "賽程訂閱", "href": "/"},
    ],
}


def site_for(comp: dict) -> dict:
    """Resolve a comp to its site-identity dict. Sport read off the comp's top-level
    `sport` (falls back to the schema block, then soccer). Soccer -> SOCCER_SITE."""
    sport = (comp.get("sport") or comp.get("schema", {}).get("sport") or "soccer").lower()
    return SITES.get(sport, SOCCER_SITE)


def effective_status(comp: dict, today: datetime.date = None) -> str:
    """Resolve display status. `status` is authored intent; once past `archive_after`
    the competition is treated as archived (drives index/homepage placement). Data-
    driven so the 2026-07-19 World Cup → archive transition is a no-op rebuild."""
    if today is None:
        today = datetime.date.today()
    aft = comp.get("archive_after")
    if aft:
        try:
            if today > datetime.date.fromisoformat(aft):
                return "archived"
        except ValueError:
            pass
    return comp.get("status", "live")


# ---------- site-wide GA4 (同步 public/index.html) ----------
def ga_snippet(site: dict = None) -> str:
    """Per-site GA4 tag. Defaults to the soccer/world-cup property so legacy
    public/ output stays byte-identical; baseball passes its own ga_id (sites.json)."""
    gid = (site or {}).get("ga_id") or "G-V12JQHW84K"
    return (
        "<!-- Google tag (gtag.js) -->\n"
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={gid}"></script>\n'
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{gid}');\n"
        "</script>"
    )


GA_SNIPPET = ga_snippet()


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


# ---------- shared site header (article + index) ----------

SITE_HEADER_CSS = """
.site-header {
  display: flex; justify-content: space-between; align-items: flex-end;
  padding: 36px 0 20px; margin-bottom: 44px;
  border-bottom: 1px solid var(--line);
  gap: 24px; flex-wrap: wrap;
}
.brand-block { display: flex; flex-direction: column; gap: 6px; }
.brand-mark {
  font-family: var(--font-display); font-size: 30px; line-height: 1;
  color: var(--accent); letter-spacing: 1.2px;
  text-decoration: none; transition: color 0.15s ease;
}
.brand-mark:hover { color: var(--accent-bright); }
.brand-tag {
  font-family: var(--font-mono); font-size: 10.5px;
  letter-spacing: 2.5px; color: var(--dim); text-transform: uppercase;
}
.site-nav {
  display: flex; gap: 22px; align-items: center;
  font-family: var(--font-mono); font-size: 11.5px;
  letter-spacing: 2px; text-transform: uppercase;
}
.site-nav a {
  color: var(--dim); text-decoration: none;
  padding: 6px 0; border-bottom: 1.5px solid transparent;
  transition: color 0.15s ease, border-color 0.15s ease;
}
.site-nav a:hover, .site-nav a.active {
  color: var(--accent); border-bottom-color: var(--accent);
}
@media (max-width: 580px) {
  .site-header { padding-top: 22px; gap: 16px; }
  .brand-mark { font-size: 24px; }
  .site-nav { gap: 16px; font-size: 11px; }
}
.site-disclaimer { font-size: 11px; color: var(--faint); line-height: 1.7; text-align: center; max-width: 600px; margin: 18px auto 0; }
.site-disclaimer span { opacity: 0.75; }
"""

# 非官方聲明（全 surface footer）— 降低 false-affiliation 商標風險（nominative fair use 硬化）
DISCLAIMER_HTML = (
    '<div class="site-disclaimer">本站為非官方球迷資訊站，與 FIFA／國際足總無任何關聯或授權；'
    '賽程與比分資料整理自公開來源。<br>'
    '<span>Unofficial fan-made site · Not affiliated with, endorsed by, or sponsored by FIFA.</span></div>'
)

BASEBALL_DISCLAIMER_HTML = (
    '<div class="site-disclaimer">本站為非官方棒球資訊站，與 MLB、中華職棒（CPBL）等職業聯盟、'
    '球團無任何關聯或授權；數據與比分整理自公開官方來源並標註。<br>'
    '<span>Unofficial fan-made site · Not affiliated with, endorsed by, or sponsored by MLB or CPBL.</span></div>'
)


def site_header_html(active: str, site: dict = None) -> str:
    """active: nav key to mark current ('home'|'standings'|'articles'|...).
    site: per-sport identity (brand_mark/brand_tag/nav/external_link). None -> soccer
    (reproduces the legacy @FOOOTBALL header byte-for-byte)."""
    site = site or SOCCER_SITE
    parts = []
    for n in site.get("nav", []):
        cls = ' class="active"' if n.get("key") == active else ""
        parts.append(f'<a href="{n["href"]}"{cls}>{n["label"]}</a>')
    ext = site.get("external_link")
    if ext:
        parts.append(f'<a href="{ext["href"]}" target="_blank" rel="noopener">{ext["label"]}</a>')
    links = "\n      ".join(parts)
    return f"""
  <header class="site-header">
    <div class="brand-block">
      <a href="/" class="brand-mark">{site["brand_mark"]}</a>
      <div class="brand-tag">{site["brand_tag"]}</div>
    </div>
    <nav class="site-nav">
      {links}
    </nav>
  </header>
"""


def theme_switch_html(site: dict = None) -> str:
    """Color switcher. Soccer -> the legacy 7-dot palette (byte-identical). Baseball -> none:
    @baseball commits to a single dark navy/gold brand (a switcher to light themes would
    undercut it); the dark theme applies via <html data-theme="navy">, no JS needed."""
    site = site or SOCCER_SITE
    if site.get("default_theme", "grass") != "navy":
        return THEME_SWITCH_HTML
    return ""


def theme_switch_js(site: dict = None) -> str:
    """Theme init/persist JS. Soccer -> legacy (default grass). Baseball -> none (fixed navy)."""
    site = site or SOCCER_SITE
    if site.get("default_theme", "grass") != "navy":
        return THEME_SWITCH_JS
    return ""


def extra_theme_css(site: dict = None) -> str:
    """Per-sport extra theme rules injected into the page <style>. Empty for soccer (so the
    soccer pages are byte-identical). Baseball = DARK navy/gold: deep navy bg + cream text +
    gold accent — one coherent dark brand across landing / articles / teams / article body
    (matches the dark text-only covers; mirrors the built-in `dark` theme but navy not green).
    All article/team CSS is var-driven, so this single override flips the whole baseball site."""
    site = site or SOCCER_SITE
    if site.get("default_theme", "grass") != "navy":
        return ""
    return """
:root[data-theme="navy"] {
  --surface:#10294a; --surface-2:#16335a; --surface-3:#1b3c69;
  --fg:#f3efe4; --fg-soft:#c7cfdb; --dim:#94a0b4; --faint:#6c7a92;
  --line:rgba(243,239,228,0.12); --line-2:rgba(243,239,228,0.20);
  --sheet-shadow:rgba(0,0,0,0.5); --scrim:rgba(0,0,0,0.5);
  --bg:#0a1f3c; --bg-glow:#0e2547;
  --accent:#e8b84b; --accent-bright:#f3c860; --accent-ink:#0a1f3c;
  --accent-soft:rgba(232,184,75,0.12); --accent-line:rgba(232,184,75,0.36); --accent-glow:rgba(232,184,75,0.30);
}
:root[data-theme="navy"] body::before { mix-blend-mode:screen; opacity:0.18; }
:root[data-theme="navy"] .site-header { position:sticky; top:0; z-index:30; margin-bottom:34px;
  padding:14px 0; background:rgba(8,24,46,0.86); backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line); }
:root[data-theme="navy"] .site-nav a { text-transform:none; letter-spacing:1px; font-size:13px;
  padding:6px 13px; border-radius:999px; border-bottom:none; }
:root[data-theme="navy"] .site-nav a:hover { color:var(--accent); background:var(--accent-soft); border-bottom:none; }
:root[data-theme="navy"] .site-nav a.active { color:var(--accent-ink); background:var(--accent); border-bottom:none; }
:root[data-theme="navy"] .brand-tag { color:var(--dim); }
"""


def site_footer_html(site: dict = None) -> str:
    """Article-page footer. Soccer -> legacy footer byte-for-byte (CTA + Medium + disclaimer).
    Baseball -> no sales CTA (editorial no-CTA rule), baseball links + baseball disclaimer."""
    site = site or SOCCER_SITE
    cta = site.get("footer_cta")
    cta_line = f'\n    <a href="{cta["href"]}" class="cta-btn">{cta["label"]}</a>' if cta else ""
    link_parts = []
    for l in site.get("footer_links", []):
        if l.get("external"):
            link_parts.append(f'<a href="{l["href"]}" target="_blank" rel="noopener">{l["label"]}</a>')
        else:
            link_parts.append(f'<a href="{l["href"]}">{l["label"]}</a>')
    links = "\n      ".join(link_parts)
    disclaimer = BASEBALL_DISCLAIMER_HTML if site.get("default_theme") == "navy" else DISCLAIMER_HTML
    return f"""  <div class="article-footer">{cta_line}
    <div class="foot-links">
      {links}
    </div>
    {disclaimer}
  </div>"""


# ---------- shared JSON-LD helpers (structured data for SEO/GEO/AEO) ----------

def _ld(obj: dict) -> str:
    """Wrap a schema.org node as a <script type=application/ld+json> block."""
    payload = obj if "@context" in obj else {"@context": "https://schema.org", **obj}
    return ('<script type="application/ld+json">'
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "</script>")


def graph_ld(nodes: list) -> str:
    """One @graph block holding several linked nodes (Google merges by @id)."""
    nodes = [n for n in nodes if n]
    if not nodes:
        return ""
    return _ld({"@context": "https://schema.org", "@graph": nodes})


def org_node(site: dict = None) -> dict:
    site = site or SOCCER_SITE
    base = site["base"]
    return {
        "@type": "Organization",
        "@id": f"{base}/#org",
        "name": site["org_name"],
        "url": f"{base}/",
        "sameAs": site["org_same_as"],
    }


def website_node(site: dict = None) -> dict:
    site = site or SOCCER_SITE
    base = site["base"]
    return {
        "@type": "WebSite",
        "@id": f"{base}/#website",
        "name": site["website_name"],
        "url": f"{base}/",
        "inLanguage": "zh-Hant",
        "publisher": {"@id": f"{base}/#org"},
    }


def competition_node(comp: dict, site: dict = None) -> dict:
    """schema.org node for one competition, driven by the registry.

    Cups -> SportsEvent (dated, host countries); leagues -> SportsLeague (season org).
    Key insertion order is preserved so the wc2026 SportsEvent serializes byte-identical
    to the previous hardcoded tournament_node() output (json.dumps keeps insertion order).
    """
    base = (site or site_for(comp))["base"]
    s = comp["schema"]
    node = {
        "@type": s["type"],
        "@id": f"{base}/{comp['schema_id']}",
        "name": comp["name_zh"],
        "sport": s.get("sport", "Soccer"),
    }
    if s["type"] == "SportsEvent":
        node["startDate"] = comp["start_date"]
        node["endDate"] = comp["end_date"]
        node["eventStatus"] = s.get("event_status", "https://schema.org/EventScheduled")
        if "location" in s:
            node["location"] = s["location"]
    else:  # SportsLeague (round-robin / playoff leagues): season-scoped org, no dates
        node["url"] = f"{base}{comp['index']['landing']}"
    if "organizer" in s:
        node["organizer"] = {"@type": "Organization", **s["organizer"]}
    return node


def tournament_node() -> dict:
    """Back-compat alias: the 2026 FIFA World Cup SportsEvent.

    Kept (name + signature) for the whole migration because build-standings.py and
    gen-team-pages.py re-export it by name via importlib. Now sourced from the registry.
    """
    return competition_node(COMPETITIONS["wc2026"])


def breadcrumb_node(items: list) -> dict:
    """items: list of (name, url-or-None). Last item usually current page (url ok)."""
    elements = []
    for i, (name, url) in enumerate(items):
        el = {"@type": "ListItem", "position": i + 1, "name": name}
        if url:
            el["item"] = url
        elements.append(el)
    return {"@type": "BreadcrumbList", "itemListElement": elements}


# ---------- article page CSS ----------

ARTICLE_CSS = """
.container { max-width: 720px; margin: 0 auto; position: relative; z-index: 1; padding-top: 0; }

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

.article-lede {
  background: var(--surface-2); border-left: 2px solid var(--accent);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  padding: 15px 20px; margin: 0 0 34px;
}
.article-lede .lede-label {
  display: block; font-family: var(--font-mono); font-size: 10.5px;
  letter-spacing: 2.5px; text-transform: uppercase; color: var(--accent);
  font-weight: 700; margin-bottom: 7px;
}
.article-lede p { font-size: 16px; color: var(--fg); line-height: 1.7; margin: 0; }

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
.prose table {
  width: 100%; border-collapse: collapse; margin: 28px 0;
  font-size: 14.5px; line-height: 1.55; overflow: hidden;
  border-radius: var(--radius-sm); box-shadow: 0 4px 16px var(--sheet-shadow);
}
.prose thead { background: var(--surface-2); }
.prose th {
  padding: 12px 14px; text-align: left; font-weight: 700; color: var(--fg);
  border-bottom: 2px solid var(--accent-line); letter-spacing: 0.4px; font-size: 13.5px;
}
.prose td {
  padding: 11px 14px; border-bottom: 1px solid var(--line);
  vertical-align: top; color: var(--fg-soft);
}
.prose tbody tr:last-child td { border-bottom: none; }
.prose tbody tr:hover td { background: var(--surface-2); }
.prose table strong { color: var(--accent); font-variant-numeric: tabular-nums; }
/* daily 戰報 §1 4-column table: 賽事 / 比分 / 場館 / 焦點 — explicit widths.
   只套 daily：feature/preview 的多欄表（5–6 欄）改走 auto 排版，否則第 4 欄吃滿 45%
   會把後面的欄位擠成一字一行。 */
.prose--daily table th:nth-child(1), .prose--daily table td:nth-child(1) { width: 24%; }
.prose--daily table th:nth-child(2), .prose--daily table td:nth-child(2) { width: 9%; text-align: center; white-space: nowrap; }
.prose--daily table th:nth-child(3), .prose--daily table td:nth-child(3) { width: 22%; }
.prose--daily table th:nth-child(4), .prose--daily table td:nth-child(4) { width: 45%; }
@media (max-width: 640px) {
  .prose table { font-size: 13px; }
  .prose th, .prose td { padding: 9px 10px; }
  .prose--daily table th:nth-child(3), .prose--daily table td:nth-child(3) { font-size: 12px; }
}
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

/* ---- series nav: 前一日 / 後一日 + 更多每日戰報 ---- */
.post-nav { margin-top: 56px; padding-top: 30px; border-top: 1px solid var(--line); }
.post-nav-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.post-nav-link {
  display: flex; flex-direction: column; gap: 6px;
  padding: 15px 18px; border: 1px solid var(--line); border-radius: var(--radius-sm);
  background: var(--surface); text-decoration: none;
  transition: border-color 0.18s ease, transform 0.18s ease, box-shadow 0.18s ease;
}
.post-nav-link:hover { border-color: var(--accent-line); transform: translateY(-2px); box-shadow: 0 10px 26px var(--sheet-shadow); }
.post-nav-link.next { text-align: right; align-items: flex-end; }
.post-nav-link.empty { border: none; background: transparent; pointer-events: none; }
.post-nav-link.fallback { background: var(--surface-2); border-style: dashed; justify-content: center; }
.post-nav-link.fallback .pn-dir { color: var(--dim); }
.post-nav-link.fallback .pn-title { color: var(--fg-soft); font-weight: 600; }
.pn-dir { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 1.8px; color: var(--accent); text-transform: uppercase; font-weight: 700; }
.pn-title { font-size: 14.5px; font-weight: 700; color: var(--fg); line-height: 1.45;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.pn-date { font-family: var(--font-mono); font-size: 11px; color: var(--dim); letter-spacing: 1px; }
.more-dailies { margin-top: 30px; }
.md-label { display: flex; align-items: center; gap: 12px; font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px; color: var(--dim); text-transform: uppercase; margin-bottom: 12px; }
.md-label::before { content: ''; width: 20px; height: 2px; background: var(--accent); }
.md-list { display: flex; flex-direction: column; }
.md-list a { display: flex; gap: 14px; align-items: baseline; padding: 12px 4px; border-bottom: 1px solid var(--line); text-decoration: none; color: var(--fg-soft); transition: color 0.15s ease; }
.md-list a:last-child { border-bottom: none; }
.md-list a:hover { color: var(--accent); }
.md-list .md-date { font-family: var(--font-mono); font-size: 11.5px; color: var(--dim); white-space: nowrap; letter-spacing: 0.5px; }
.md-list .md-ttl { font-size: 14px; font-weight: 600; line-height: 1.4; flex: 1;
  display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
@media (max-width: 560px) {
  .post-nav-pair { grid-template-columns: 1fr; }
  .post-nav-link.next { text-align: left; align-items: flex-start; }
  .post-nav-link.empty { display: none; }
}
"""


# ---------- index page CSS ----------

INDEX_CSS = """
.container { max-width: 1100px; margin: 0 auto; position: relative; z-index: 1; padding-top: 0; }
.idx-h1 {
  font-family: var(--font-display); font-weight: 400;
  font-size: clamp(28px, 4.4vw, 42px); line-height: 1.12;
  color: var(--fg); letter-spacing: 0.4px; margin-bottom: 10px;
}
.idx-intro {
  font-size: 14px; color: var(--fg-soft); letter-spacing: 0.2px;
  margin-bottom: 44px;
}

/* ---- feature article (first / most important) ---- */
.idx-feature {
  display: grid; grid-template-columns: 1.35fr 1fr; gap: 40px;
  align-items: center; margin-bottom: 60px;
  text-decoration: none; color: inherit;
}
.idx-feature-img-wrap { position: relative; overflow: hidden; border-radius: var(--radius); }
.idx-feature-img {
  width: 100%; height: 340px; object-fit: cover; display: block;
  box-shadow: 0 14px 36px var(--sheet-shadow);
  transition: transform 0.32s cubic-bezier(0.22,1,0.36,1);
}
.idx-feature:hover .idx-feature-img { transform: scale(1.03); }
.idx-feature-body { display: flex; flex-direction: column; gap: 16px; }
.idx-feature-kicker {
  display: inline-flex; align-items: center; gap: 8px;
  background: var(--accent); color: var(--accent-ink);
  padding: 6px 14px; border-radius: 99px;
  font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 2.5px;
  text-transform: uppercase; font-weight: 700; align-self: flex-start;
}
.idx-feature-title {
  font-family: var(--font-display); font-weight: 400;
  font-size: clamp(26px, 3.2vw, 36px); line-height: 1.2;
  color: var(--fg); letter-spacing: 0.3px;
}
.idx-feature-excerpt {
  font-size: 16px; color: var(--fg-soft); line-height: 1.7;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}
.idx-feature-meta {
  font-family: var(--font-mono); font-size: 12px; color: var(--dim);
  letter-spacing: 1px; padding-top: 4px;
}

/* ---- section label ---- */
.idx-section-label {
  display: flex; align-items: center; gap: 13px;
  font-family: var(--font-mono); font-size: 11px; letter-spacing: 3px;
  color: var(--dim); text-transform: uppercase;
  margin-bottom: 22px;
}
.idx-section-label::before { content: ''; width: 22px; height: 2px; background: var(--accent); }
.idx-section-label .gt-rule { flex: 1; height: 1px; background: var(--line); margin-left: 4px; }

/* ---- 3-col grid ---- */
.idx-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }
.idx-card {
  display: flex; flex-direction: column;
  background: var(--surface); border: 1px solid var(--line);
  border-radius: var(--radius); overflow: hidden;
  text-decoration: none; color: inherit;
  transition: transform 0.22s cubic-bezier(0.22,1,0.36,1), border-color 0.2s ease, box-shadow 0.2s ease;
}
.idx-card:hover { transform: translateY(-4px); border-color: var(--accent-line); box-shadow: 0 14px 32px var(--sheet-shadow); }
.idx-card-img-wrap { position: relative; overflow: hidden; }
.idx-card-img { width: 100%; height: 170px; object-fit: cover; display: block; transition: transform 0.32s cubic-bezier(0.22,1,0.36,1); }
.idx-card:hover .idx-card-img { transform: scale(1.04); }
.idx-card-body { padding: 16px 18px 18px; display: flex; flex-direction: column; gap: 9px; flex: 1; }
.idx-card-kicker {
  display: inline-flex; align-items: center; gap: 7px;
  font-family: var(--font-mono); font-size: 10px; letter-spacing: 2.5px;
  text-transform: uppercase; font-weight: 700; color: var(--accent);
  align-self: flex-start;
}
.idx-card-kicker::before { content: ''; width: 12px; height: 2px; background: var(--accent); }
.idx-card-title {
  font-size: 15.5px; font-weight: 700; color: var(--fg); line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical;
  overflow: hidden; letter-spacing: 0.2px;
}
.idx-card-meta { font-family: var(--font-mono); font-size: 11px; color: var(--dim); margin-top: auto; padding-top: 8px; letter-spacing: 1px; }

/* ---- responsive ---- */
@media (max-width: 900px) {
  .idx-grid { grid-template-columns: repeat(2, 1fr); }
  .idx-feature { grid-template-columns: 1fr; gap: 22px; }
  .idx-feature-img { height: 260px; }
}
@media (max-width: 580px) {
  .container { padding-top: 38px; }
  .idx-grid { grid-template-columns: 1fr; }
  .idx-feature-img { height: 200px; }
  .idx-feature-title { font-size: 24px; }
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
    """Strip [📸 插入 PNG: filename] placeholders. The PNG is a Medium-only
    artifact — on this site we already render the §1/§2 markdown table /
    bullet list as HTML, which is both SEO-/GEO-indexable and visually
    cleaner. Keeping the PNG inline would duplicate the same content twice."""
    return re.sub(r"\[📸 插入 PNG: [^\]]+?\]\s*\n?", "", body)


def strip_h1(body: str) -> str:
    """Drop the first H1 (we render title via the article header)."""
    return re.sub(r"^# .*\n", "", body, count=1).lstrip("\n")


def extract_excerpt(body: str, length: int = 120) -> str:
    """Pull the first prose paragraph (skip headings, images, blockquotes,
    horizontal rules) and truncate. Strips inline markdown markers."""
    for raw in body.split("\n\n"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("#", "!", ">", "---", "```", "|")):
            continue
        if line.startswith(("- ", "* ", "1.")):
            continue
        # skip a bold-only standfirst / volume marker line (e.g. **... Vol. 004**)
        # — it just duplicates the subtitle and makes a useless excerpt.
        if line.startswith("**") and line.endswith("**") and line.count("**") == 2:
            continue
        # strip inline md: **bold** _em_ `code` [text](url)
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        line = re.sub(r"\*(.+?)\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("\n", " ").strip()
        if len(line) > length:
            return line[:length].rstrip() + "…"
        return line
    return ""


def _strip_inline_md(s: str) -> str:
    """Drop inline markdown markers so schema text matches the rendered plain text."""
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    return s.strip()


FAQ_HEADING_RE = re.compile(r"(?m)^##[ \t]+(?:常見問題|常見問答|FAQ)[ \t]*$")


def parse_faq(body: str):
    """Extract (question, answer) pairs from a '## 常見問題' section so we can emit
    FAQPage schema. The section itself stays in the body and renders as normal
    prose (h2 + h3 + p), so the schema text always matches the visible text.

    Convention: each item is a '### 問句？' heading followed by one or more
    paragraphs of answer, until the next '###' or a new '##' section / EOF.
    We NEVER synthesise FAQ text here — only mirror what the author wrote.
    """
    m = FAQ_HEADING_RE.search(body)
    if not m:
        return []
    section = body[m.end():]
    nxt = re.search(r"(?m)^##[ \t]+\S", section)  # stop at next level-2 heading
    if nxt:
        section = section[:nxt.start()]
    pairs = []
    for part in re.split(r"(?m)^###[ \t]+", section)[1:]:
        head, _, rest = part.partition("\n")
        q = _strip_inline_md(head.strip())
        a = _strip_inline_md(" ".join(
            ln.strip() for ln in rest.splitlines() if ln.strip()))
        if q and a:
            pairs.append((q, a))
    return pairs


def faq_node(pairs, page_url: str):
    """schema.org FAQPage node from (q, a) pairs, or None when empty."""
    if not pairs:
        return None
    return {
        "@type": "FAQPage",
        "@id": f"{page_url}#faq",
        "inLanguage": "zh-Hant",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in pairs
        ],
    }


# ---------- render ----------

def render_article(meta: dict, body_html: str, slug: str, excerpt: str = "",
                   prev_nav=None, next_nav=None, more_dailies=None, nav_kind="daily",
                   faq=None) -> str:
    typ = meta.get("type", "feature")
    if typ == "daily":
        vol = meta.get("vol", "?")
        kicker = f"DAILY · VOL. {int(vol):03d}" if isinstance(vol, int) else f"DAILY · VOL. {vol}"
    else:
        kicker = "FEATURE"
    title_raw = meta.get("title", slug)
    title_safe = html_lib.escape(title_raw)
    # seo_title overrides ONLY the <title> element (SERP headline / ranking
    # signal); visible H1, og/twitter title and JSON-LD headline stay on title.
    seo_title_raw = str(meta.get("seo_title", "")).strip() or title_raw
    seo_title_safe = html_lib.escape(seo_title_raw)
    subtitle_raw = meta.get("subtitle", "")
    subtitle = html_lib.escape(subtitle_raw)
    lede_raw = str(meta.get("lede", "")).strip()
    date_str = str(meta.get("date", ""))
    try:
        d = datetime.date.fromisoformat(date_str)
        date_disp = f"{d.year}/{d.month:02d}/{d.day:02d} · {WEEKDAY_ZH[d.weekday()]}"
    except Exception:
        date_disp = date_str

    # meta description: prefer the subtitle, enrich with the first paragraph when
    # thin (daily subtitles like "Vol. 00x" are too short to be useful for SEO).
    desc_raw = subtitle_raw.strip()
    if len(desc_raw) < 60 and excerpt and excerpt not in desc_raw and desc_raw not in excerpt:
        desc_raw = f"{desc_raw}　{excerpt}".strip("　 ") if desc_raw else excerpt
    if not desc_raw:
        desc_raw = excerpt or title_raw
    if lede_raw:  # purpose-written short answer beats subtitle/excerpt for description
        desc_raw = lede_raw
    desc_raw = desc_raw[:150].rstrip("　 ·，、")
    desc_safe = html_lib.escape(desc_raw)
    cover_alt = html_lib.escape(f"{title_raw}｜封面")

    # structured data: Article + breadcrumb (+ org/website context)
    # competition the article belongs to (defaults to wc2026 → existing articles
    # need no frontmatter edit and emit byte-identical JSON-LD).
    comp = COMPETITIONS.get(meta.get("competition", "wc2026")) or COMPETITIONS.get("wc2026")
    # site identity follows the comp's sport; soccer comps -> SOCCER_SITE (base == SITE)
    # so every SITE-derived URL below stays byte-identical for existing articles.
    site = site_for(comp)
    base = site["base"]
    art_type = "NewsArticle" if typ == "daily" else "Article"
    page_url = f"{base}/articles/{slug}/"
    article_ld = {
        "@type": art_type,
        "headline": title_raw,
        "description": desc_raw,
        "image": f"{base}/articles/{slug}/cover.png",
        "inLanguage": "zh-Hant",
        "url": page_url,
        "mainEntityOfPage": page_url,
        "author": {"@id": f"{base}/#org"},
        "publisher": {"@id": f"{base}/#org"},
        "isPartOf": {"@id": f"{base}/{comp['schema_id']}"},
    }
    if date_str:
        article_ld["datePublished"] = date_str
        article_ld["dateModified"] = date_str
    crumb = breadcrumb_node([
        ("首頁", f"{base}/"),
        ("文章", f"{base}/articles/"),
        (title_raw, page_url),
    ])
    jsonld = graph_ld([org_node(site), website_node(site), competition_node(comp, site),
                       article_ld, crumb, faq_node(faq, page_url)])

    # ----- prev/next nav + 更多每日戰報 (internal linking for SEO/engagement) -----
    # daily 走「前一日/後一日戰報」(daily 連載)；feature 走「前一篇/後一篇」(feature 之間，
    # 例如 AI 圓桌三部曲)。邊界缺一側時補「所有文章」連結，不留白。
    def _dl(a):
        return (a["slug"],
                html_lib.escape(str(a["meta"].get("title", a["slug"]))),
                _date_disp(str(a["meta"].get("date", ""))))
    prev_lbl, next_lbl = ("前一篇", "後一篇") if nav_kind == "feature" else ("前一日戰報", "後一日戰報")
    FALLBACK_TITLE = "瀏覽全部戰報與文章"

    head_rels = ""
    if prev_nav:
        head_rels += f'\n<link rel="prev" href="{base}/articles/{prev_nav["slug"]}/">'
    if next_nav:
        head_rels += f'\n<link rel="next" href="{base}/articles/{next_nav["slug"]}/">'

    if prev_nav:
        s, t, dt = _dl(prev_nav)
        prev_link = (f'<a class="post-nav-link prev" href="/articles/{s}/">'
                     f'<span class="pn-dir">← {prev_lbl}</span>'
                     f'<span class="pn-title">{t}</span><span class="pn-date">{dt}</span></a>')
    else:
        prev_link = ('<a class="post-nav-link prev fallback" href="/articles/">'
                     '<span class="pn-dir">← 所有文章</span>'
                     f'<span class="pn-title">{FALLBACK_TITLE}</span></a>')
    if next_nav:
        s, t, dt = _dl(next_nav)
        next_link = (f'<a class="post-nav-link next" href="/articles/{s}/">'
                     f'<span class="pn-dir">{next_lbl} →</span>'
                     f'<span class="pn-title">{t}</span><span class="pn-date">{dt}</span></a>')
    else:
        next_link = ('<a class="post-nav-link next fallback" href="/articles/">'
                     '<span class="pn-dir">所有文章 →</span>'
                     f'<span class="pn-title">{FALLBACK_TITLE}</span></a>')

    more = more_dailies or []
    if more:
        rows = ""
        for a in more:
            s, t, dt = _dl(a)
            rows += (f'<a href="/articles/{s}/"><span class="md-date">{dt}</span>'
                     f'<span class="md-ttl">{t}</span></a>')
        more_block = ('<div class="more-dailies"><div class="md-label">更多每日戰報</div>'
                      f'<div class="md-list">{rows}</div></div>')
    else:
        more_block = ""

    series_nav = (f'<nav class="post-nav" aria-label="文章導覽">'
                  f'<div class="post-nav-pair">{prev_link}{next_link}</div>'
                  f'{more_block}</nav>')

    # ----- short-answer lede (AEO 短答；早於封面、DOM 高位) -----
    lede_html = ""
    if lede_raw:
        lede_html = ('\n    <div class="article-lede"><span class="lede-label">重點速答</span>'
                     f'<p>{html_lib.escape(lede_raw)}</p></div>')

    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="{site['default_theme']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{seo_title_safe} | {site['title_suffix']}</title>
<meta name="description" content="{desc_safe}">
<meta property="og:title" content="{title_safe}">
<meta property="og:description" content="{desc_safe}">
<meta property="og:image" content="{base}/articles/{slug}/cover.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:type" content="article">
<meta property="og:url" content="{base}/articles/{slug}/">
<meta property="og:site_name" content="{site['org_name']}">
<meta property="og:locale" content="zh_TW">
<meta property="article:published_time" content="{date_str}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title_safe}">
<meta name="twitter:description" content="{desc_safe}">
<meta name="twitter:image" content="{base}/articles/{slug}/cover.png">
<link rel="canonical" href="{base}/articles/{slug}/">{head_rels}
<link rel="alternate" type="application/rss+xml" title="{site['feed_title']}" href="{base}/feed.xml">
{jsonld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{ga_snippet(site)}
<style>
{SHARED_TOKENS_CSS}{extra_theme_css(site)}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{ARTICLE_CSS}
</style>
</head>
<body>
{theme_switch_html(site)}
<div class="container">{site_header_html("articles", site)}
  <article>
    <header class="article-header">
      <div class="article-kicker">{kicker}</div>
      <h1 class="article-title">{title_safe}</h1>
      <div class="article-subtitle">{subtitle}</div>
      <div class="article-meta">{date_disp}</div>
    </header>{lede_html}
    <img class="article-cover" src="cover.png" alt="{cover_alt}">
    <div class="prose{' prose--daily' if typ == 'daily' else ''}">
{body_html}
    </div>
  </article>
  {series_nav}
{site_footer_html(site)}
</div>
<script>{theme_switch_js(site)}</script>
</body>
</html>
"""


def _kicker_label(meta: dict) -> str:
    if meta.get("type") == "daily":
        vol = meta.get("vol", "?")
        return f"DAILY · VOL. {int(vol):03d}" if isinstance(vol, int) else f"DAILY · VOL. {vol}"
    return "FEATURE"


def _date_disp(date_str: str) -> str:
    try:
        d = datetime.date.fromisoformat(date_str)
        return f"{d.year}/{d.month:02d}/{d.day:02d} · {WEEKDAY_ZH[d.weekday()]}"
    except Exception:
        return date_str


def render_index(articles: list) -> str:
    if not articles:
        feature_html = ""
        grid_html = ""
    else:
        feat = articles[0]
        feat_kicker = _kicker_label(feat["meta"])
        feat_title = html_lib.escape(feat["meta"].get("title", feat["slug"]))
        feat_excerpt = html_lib.escape(feat.get("excerpt") or feat["meta"].get("subtitle", ""))
        feat_meta = _date_disp(str(feat["meta"].get("date", "")))
        feature_html = f"""
  <a class="idx-feature" href="/articles/{feat['slug']}/">
    <div class="idx-feature-img-wrap"><img class="idx-feature-img" src="/articles/{feat['slug']}/cover.png" alt="{feat_title}｜封面"></div>
    <div class="idx-feature-body">
      <span class="idx-feature-kicker">{feat_kicker}</span>
      <h2 class="idx-feature-title">{feat_title}</h2>
      <div class="idx-feature-excerpt">{feat_excerpt}</div>
      <div class="idx-feature-meta">{feat_meta}</div>
    </div>
  </a>"""

        cards = ""
        for a in articles[1:]:
            kicker = _kicker_label(a["meta"])
            title = html_lib.escape(a["meta"].get("title", a["slug"]))
            date_disp = _date_disp(str(a["meta"].get("date", "")))
            cards += f"""
      <a class="idx-card" href="/articles/{a['slug']}/">
        <div class="idx-card-img-wrap"><img class="idx-card-img" src="/articles/{a['slug']}/cover.png" alt="{title}｜封面"></div>
        <div class="idx-card-body">
          <span class="idx-card-kicker">{kicker}</span>
          <div class="idx-card-title">{title}</div>
          <div class="idx-card-meta">{date_disp}</div>
        </div>
      </a>"""

        grid_html = f"""
  <div class="idx-section-label">更多文章 <span class="gt-rule"></span></div>
  <div class="idx-grid">{cards}
  </div>""" if cards else ""

    # structured data: CollectionPage + ItemList of all articles + breadcrumb
    item_list = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1,
             "url": f"{SITE}/articles/{a['slug']}/",
             "name": a["meta"].get("title", a["slug"])}
            for i, a in enumerate(articles)
        ],
    }
    collection = {
        "@type": "CollectionPage",
        "@id": f"{SITE}/articles/",
        "url": f"{SITE}/articles/",
        "name": "文章 — 2026 世界盃每日戰報與焦點觀察",
        "inLanguage": "zh-Hant",
        "isPartOf": {"@id": f"{SITE}/#website"},
        "mainEntity": item_list,
    }
    idx_crumb = breadcrumb_node([("首頁", f"{SITE}/"), ("文章", f"{SITE}/articles/")])
    idx_jsonld = graph_ld([org_node(), website_node(), collection, idx_crumb])

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
<meta property="og:url" content="https://foootball.twtools.cc/articles/">
<meta property="og:image" content="https://foootball.twtools.cc/og-home.png">
<meta property="og:image:width" content="2400">
<meta property="og:image:height" content="1260">
<meta property="og:site_name" content="@foootball">
<meta property="og:locale" content="zh_TW">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="文章 — @foootball 世界盃">
<meta name="twitter:description" content="每日戰報、規則解讀、焦點觀察。">
<meta name="twitter:image" content="https://foootball.twtools.cc/og-home.png">
<link rel="canonical" href="https://foootball.twtools.cc/articles/">
<link rel="alternate" type="application/rss+xml" title="@foootball 最新文章" href="https://foootball.twtools.cc/feed.xml">
{idx_jsonld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{GA_SNIPPET}
<style>
{SHARED_TOKENS_CSS}
{THEME_SWITCH_CSS}
{SITE_HEADER_CSS}
{INDEX_CSS}
</style>
</head>
<body>
{THEME_SWITCH_HTML}
<div class="container">{site_header_html("articles")}
  <h1 class="idx-h1">文章 — 2026 世界盃每日戰報與焦點觀察</h1>
  <div class="idx-intro">每日戰報 · 焦點觀察 · 規則解讀 — 全部繁體中文 / 台北時間</div>
{feature_html}
{grid_html}
  <footer style="margin-top:56px;padding-top:26px;border-top:1px solid var(--line);">{DISCLAIMER_HTML}</footer>
</div>
<script>{THEME_SWITCH_JS}</script>
</body>
</html>
"""


# ---------- RSS feed ----------
# RFC-822 date 用固定英文縮寫（build 環境 locale 不定，不靠 strftime("%a")）。
_RFC822_DAY = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_RFC822_MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
FEED_MAX = 30  # feed 只收最近 N 篇


def _rfc822(date_str: str) -> str:
    """YYYY-MM-DD → 'Sun, 08 Jun 2026 08:00:00 +0800'（固定台北早上 8 點）。"""
    try:
        d = datetime.date.fromisoformat(date_str)
    except Exception:
        return ""
    return (f"{_RFC822_DAY[d.weekday()]}, {d.day:02d} {_RFC822_MON[d.month - 1]} "
            f"{d.year} 08:00:00 +0800")


def render_feed(articles: list, site: dict = None) -> str:
    """RSS 2.0 feed（<site>/feed.xml）。收最近 FEED_MAX 篇 daily+feature；
    description 優先用 lede（重點速答）→ excerpt → subtitle，全為已可見文字。
    site=None -> soccer（byte-identical 合約）。"""
    site = site or SOCCER_SITE
    base = site["base"]
    items = articles[:FEED_MAX]
    last_build = _rfc822(str(items[0]["meta"].get("date", ""))) if items else ""

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        f"    <title>{site['feed_channel_title']}</title>",
        f"    <link>{base}/articles/</link>",
        f'    <atom:link href="{base}/feed.xml" rel="self" type="application/rss+xml" />',
        f"    <description>{site['feed_channel_desc']}</description>",
        "    <language>zh-Hant</language>",
    ]
    if last_build:
        lines.append(f"    <lastBuildDate>{last_build}</lastBuildDate>")
    for a in items:
        meta = a["meta"]
        url = f"{base}/articles/{a['slug']}/"
        title = html_lib.escape(str(meta.get("title", a["slug"])))
        desc_src = (str(meta.get("lede", "")).strip()
                    or a.get("excerpt") or str(meta.get("subtitle", "")))
        desc = html_lib.escape(_strip_inline_md(desc_src))
        cat = "每日戰報" if meta.get("type") == "daily" else "專題"
        pub = _rfc822(str(meta.get("date", "")))
        lines.append("    <item>")
        lines.append(f"      <title>{title}</title>")
        lines.append(f"      <link>{url}</link>")
        lines.append(f'      <guid isPermaLink="true">{url}</guid>')
        if pub:
            lines.append(f"      <pubDate>{pub}</pubDate>")
        lines.append(f"      <category>{html_lib.escape(cat)}</category>")
        lines.append(f"      <description>{desc}</description>")
        lines.append("    </item>")
    lines.append("  </channel>")
    lines.append("</rss>")
    lines.append("")
    return "\n".join(lines)


# ---------- per-sport site routing (multi-site build) ----------
# A comp's sport decides which static site it builds into. Soccer -> public/ (the existing
# foootball site, untouched / byte-identical). Non-soccer sports -> public-<sport>/ with their
# own landing + sitemap and their own base URL (baseball.twtools.cc). render_index/render_feed
# stay soccer-only so the foootball output never changes.
PUB_SOCCER = ROOT / "public"


def _comp_of(meta: dict) -> dict:
    return COMPETITIONS.get(meta.get("competition", "wc2026")) or COMPETITIONS["wc2026"]


def _sport_of(meta: dict) -> str:
    comp = _comp_of(meta)
    return (comp.get("sport") or comp.get("schema", {}).get("sport") or "soccer").lower()


def pub_root_for(meta: dict) -> pathlib.Path:
    sport = _sport_of(meta)
    return PUB_SOCCER if sport == "soccer" else ROOT / f"public-{sport}"


# Landing + article-index card CSS for non-soccer sites. Var-driven → inherits the dark navy
# tokens from extra_theme_css(navy), so the landing/list match the article & team pages exactly.
BB_LANDING_CSS = """
.bb-shell{max-width:1060px;margin:0 auto}
.bb-hero{padding:30px 2px 26px}
.bb-hero h1{font-family:var(--font-display);font-size:clamp(30px,5vw,48px);line-height:1.08;letter-spacing:.5px;color:var(--fg)}
.bb-hero p{font-size:16.5px;color:var(--fg-soft);line-height:1.75;max-width:64ch;margin-top:14px}
.bb-sec{display:flex;align-items:baseline;gap:12px;margin:36px 2px 16px}
.bb-sec h2{font-family:var(--font-mono);font-size:12px;letter-spacing:2.5px;text-transform:uppercase;color:var(--dim);font-weight:700}
.bb-sec .ln{flex:1;height:1px;background:var(--line)}
.bb-teams{display:flex;align-items:center;gap:16px;text-decoration:none;color:inherit;
  background:var(--accent-soft);border:1px solid var(--accent-line);border-radius:var(--radius-sm);
  padding:16px 22px;margin:8px 0 4px;transition:border-color .15s,transform .15s}
.bb-teams:hover{border-color:var(--accent);transform:translateY(-2px)}
.bb-teams .ic{font-size:26px}
.bb-teams .t{font-size:17px;font-weight:800;color:var(--fg)}
.bb-teams .d{font-size:12.5px;color:var(--dim);margin-top:2px}
.bb-teams .go{margin-left:auto;color:var(--accent);font-weight:800;font-size:14px}
.cov{position:relative;overflow:hidden;background:var(--surface-2)}
.cov img{display:block;width:100%;height:100%;object-fit:cover}
.card-lead{display:block;text-decoration:none;color:inherit;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;margin-bottom:6px;transition:border-color .15s,transform .15s}
.card-lead:hover{border-color:var(--accent-line);transform:translateY(-2px)}
.card-lead .cov{aspect-ratio:1200/470}
.card-lead .body{padding:22px 26px}
.card-lead .kk{font-family:var(--font-mono);font-size:11px;letter-spacing:2px;color:var(--accent);font-weight:700;text-transform:uppercase}
.card-lead .tt{font-size:27px;font-weight:900;line-height:1.3;margin:9px 0;color:var(--fg)}
.card-lead .dd{font-size:14.5px;color:var(--fg-soft);line-height:1.65;max-width:62ch}
.card-lead .mm{font-size:12.5px;color:var(--faint);margin-top:12px;font-variant-numeric:tabular-nums}
.bb-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}
.card{display:grid;grid-template-columns:165px 1fr;text-decoration:none;color:inherit;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--radius-sm);overflow:hidden;transition:border-color .15s,transform .15s}
.card:hover{border-color:var(--accent-line);transform:translateY(-2px)}
.card .body{padding:15px 17px;display:flex;flex-direction:column;justify-content:center}
.card .kk{font-family:var(--font-mono);font-size:10.5px;letter-spacing:1.5px;color:var(--accent);font-weight:700;text-transform:uppercase}
.card .tt{font-size:16px;font-weight:900;line-height:1.36;margin:6px 0 0;color:var(--fg)}
.card .mm{font-size:11.5px;color:var(--faint);margin-top:9px;font-variant-numeric:tabular-nums}
.bb-faq{margin-top:14px;display:grid;gap:12px}
.bb-faq .qa{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius-sm);padding:16px 20px}
.bb-faq .faq-q{font-size:16px;font-weight:800;color:var(--fg);margin:0 0 6px;line-height:1.45}
.bb-faq .faq-a{font-size:14px;color:var(--fg-soft);line-height:1.72;margin:0}
.bb-foot{margin-top:52px;padding-top:24px;border-top:1px solid var(--line);font-size:12px;color:var(--faint);line-height:1.85}
@media(max-width:680px){.bb-grid{grid-template-columns:1fr}.card{grid-template-columns:120px 1fr}}
"""


def _bb_lead_card(a: dict) -> str:
    title = html_lib.escape(a["meta"].get("title", a["slug"]))
    desc = html_lib.escape(a.get("excerpt") or a["meta"].get("subtitle", ""))[:150]
    return f"""<a class="card-lead" href="/articles/{a['slug']}/">
    <div class="cov"><img src="/articles/{a['slug']}/cover.png" alt="{title}｜封面" loading="lazy"></div>
    <div class="body"><span class="kk">{_kicker_label(a['meta'])} · {_date_disp(str(a['meta'].get('date','')))}</span>
      <div class="tt">{title}</div><div class="dd">{desc}</div></div></a>"""


def _bb_grid_card(a: dict) -> str:
    title = html_lib.escape(a["meta"].get("title", a["slug"]))
    return f"""<a class="card" href="/articles/{a['slug']}/">
      <div class="cov"><img src="/articles/{a['slug']}/cover.png" alt="{title}｜封面" loading="lazy"></div>
      <div class="body"><span class="kk">{_kicker_label(a['meta'])}</span>
        <div class="tt">{title}</div><div class="mm">{_date_disp(str(a['meta'].get('date','')))}</div></div></a>"""


def _bb_head(site: dict, title: str, desc: str, url: str, jsonld: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-Hant" data-theme="{site['default_theme']}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_lib.escape(title)}</title>
<meta name="description" content="{html_lib.escape(desc)}">
<meta property="og:title" content="{html_lib.escape(title)}">
<meta property="og:description" content="{html_lib.escape(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{site['base']}/og-home.png">
<meta property="og:image:width" content="2400">
<meta property="og:image:height" content="1260">
<meta property="og:site_name" content="{html_lib.escape(site['org_name'])}">
<meta property="og:locale" content="zh_TW">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{html_lib.escape(title)}">
<meta name="twitter:description" content="{html_lib.escape(desc)}">
<meta name="twitter:image" content="{site['base']}/og-home.png">
<meta name="theme-color" content="#0a1f3c">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<link rel="canonical" href="{url}">
<link rel="alternate" type="application/rss+xml" title="{site['feed_title']}" href="{site['base']}/feed.xml">
{jsonld}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700;900&display=swap" rel="stylesheet">
{ga_snippet(site)}
<style>
{SHARED_TOKENS_CSS}{extra_theme_css(site)}
{SITE_HEADER_CSS}
{BB_LANDING_CSS}
</style>
</head>"""


def _bb_footer(site: dict) -> str:
    ext = site.get("external_link")
    social = (f'　·　<a href="{ext["href"]}" target="_blank" rel="noopener" '
              f'style="color:var(--accent)">{ext["label"]}</a>') if ext else ""
    return (f'  <footer class="bb-foot">{html_lib.escape(site["org_name"])} · '
            f'{site["base"].replace("https://","")}{social}<br>'
            '本站為獨立內容站，與 MLB、中華職棒（CPBL）等職業聯盟、球團無官方關聯；'
            '數據引自公開官方來源並標註。</footer>')


# 首頁可見 FAQ（＝站台事實，非杜撰；同時餵 FAQPage schema 與可見問句式標題，
# 對應測評 AEO 的「FAQ 結構 / 問句式標題 / PAA 友善」三項）。問句一律以「？」收尾。
BB_HOME_FAQ = [
    ("@baseball 的數據多久更新一次？",
     "MLB 戰績與排名每日更新，資料來自官方 MLB StatsAPI 與 api-sports；中華職棒（CPBL）隊伍與賽果同步官方公開數據。每篇文章的數字都標註來源與截止日期。"),
    ("@baseball 涵蓋哪些聯盟？",
     "目前以美國職棒大聯盟（MLB，30 隊）與中華職棒（CPBL）為主，提供球隊戰績、主客場拆分、球員名冊與里程碑特刊；日韓職棒（NPB／KBO）規劃中。"),
    ("這個網站和 MLB、中華職棒官方有關係嗎？",
     "沒有。@baseball 是獨立的繁體中文數據內容站，與 MLB、CPBL 等職業聯盟及球團無任何官方關聯；所有數據引自公開官方來源並於文中標註。"),
    ("文章的數據可信嗎？要怎麼查證？",
     "每篇深度文以結構化事實（facts pack）為基礎撰寫，數字逐筆對照 MLB StatsAPI／api-sports 官方來源，並經獨立第二來源交叉核對後才發佈。文中關鍵數據附截止日期，方便讀者自行查證。"),
    ("為什麼看 @baseball，而不是直接查比分？",
     "即時比分各家都有；@baseball 專注「看門道」——用排行榜、主客場拆分、淨勝分與里程碑脈絡把數字背後的故事說清楚，每篇 5,000 字以上、附統計表，為深度理解而非即時速報而寫。"),
]


def _bb_faq_html() -> str:
    qa = "\n".join(
        f'    <div class="qa"><h3 class="faq-q">{html_lib.escape(q)}</h3>'
        f'<p class="faq-a">{html_lib.escape(a)}</p></div>'
        for q, a in BB_HOME_FAQ)
    return ('<div class="bb-sec"><h2>常見問題</h2><span class="ln"></span></div>\n'
            f'  <section class="bb-faq">\n{qa}\n  </section>')


def render_sport_index(articles: list, site: dict, sport_label: str) -> str:
    """Dark navy/gold landing for a non-soccer site (baseball.twtools.cc): unified site header,
    hero, teams entry, featured lead article + recent grid. Shares the SHARED_TOKENS_CSS system
    (dark navy via extra_theme_css) so landing / articles index / article body / team pages are
    one coherent design. Kept separate from soccer render_index (soccer stays byte-identical)."""
    base = site["base"]
    lead = _bb_lead_card(articles[0]) if articles else ""
    grid = "\n      ".join(_bb_grid_card(a) for a in articles[1:]) if len(articles) > 1 else ""
    item_list = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": f"{base}/articles/{a['slug']}/",
         "name": a["meta"].get("title", a["slug"])} for i, a in enumerate(articles)]}
    collection = {"@type": "CollectionPage", "@id": f"{base}/", "url": f"{base}/",
                  "name": site["website_name"], "inLanguage": "zh-Hant",
                  "isPartOf": {"@id": f"{base}/#website"}, "mainEntity": item_list}
    jsonld = graph_ld([org_node(site), website_node(site), collection,
                       breadcrumb_node([("首頁", f"{base}/")]),
                       faq_node(BB_HOME_FAQ, f"{base}/")])
    grid_block = f'<div class="bb-sec"><h2>最新文章</h2><span class="ln"></span></div>\n    <div class="bb-grid">\n      {grid}\n    </div>' if grid else ""
    return f"""{_bb_head(site, site['website_name'], f"{sport_label}數據深度分析、里程碑特刊、戰績排行——繁體中文 / 台北時間。", f"{base}/", jsonld)}
<body>
<div class="bb-shell">{site_header_html("home", site)}
  <main>
  <section class="bb-hero">
    <h1>看門道的{sport_label}，<br>用數據說話。</h1>
    <p>中職 CPBL 與大聯盟 MLB 的數據深度分析、里程碑特刊與比賽戰報。每篇 5,000 字以上、附排行與統計表，每個數字標註官方來源。繁體中文、台北時間。</p>
  </section>
  <a class="bb-teams" href="/teams/"><span class="ic">⚾</span>
    <span><span class="t">MLB 30 隊球隊資料</span><br><span class="d">戰績 · 主客場拆分 · 球員名冊 · 逐隊一頁</span></span>
    <span class="go">看球隊 →</span></a>
  <div class="bb-sec"><h2>編輯精選</h2><span class="ln"></span></div>
  {lead}
  {grid_block}
  {_bb_faq_html()}
  </main>
{_bb_footer(site)}
</div>
</body>
</html>
"""


def render_sport_articles_index(articles: list, site: dict, sport_label: str) -> str:
    """The real /articles/ index (distinct from home — no teams hero, article-focused list).
    Fixes the earlier hole where /articles/ was a byte-identical clone of the homepage."""
    base = site["base"]
    lead = _bb_lead_card(articles[0]) if articles else ""
    grid = "\n      ".join(_bb_grid_card(a) for a in articles[1:]) if len(articles) > 1 else ""
    item_list = {"@type": "ItemList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "url": f"{base}/articles/{a['slug']}/",
         "name": a["meta"].get("title", a["slug"])} for i, a in enumerate(articles)]}
    coll = {"@type": "CollectionPage", "@id": f"{base}/articles/", "url": f"{base}/articles/",
            "name": f"{site['org_name']} 深度文章", "inLanguage": "zh-Hant",
            "isPartOf": {"@id": f"{base}/#website"}, "mainEntity": item_list}
    jsonld = graph_ld([org_node(site), website_node(site), coll,
                       breadcrumb_node([("首頁", f"{base}/"), ("文章", f"{base}/articles/")])])
    grid_block = f'\n    <div class="bb-grid">\n      {grid}\n    </div>' if grid else ""
    return f"""{_bb_head(site, f"深度文章 ｜ {site['org_name']}", f"{sport_label} CPBL 與 MLB 的數據深度分析、里程碑特刊與比賽戰報，共 {len(articles)} 篇。", f"{base}/articles/", jsonld)}
<body>
<div class="bb-shell">{site_header_html("articles", site)}
  <main>
  <section class="bb-hero" style="padding-bottom:6px">
    <h1>深度文章</h1>
    <p>中職 CPBL 與大聯盟 MLB 的數據深度分析、里程碑特刊與比賽戰報。每篇 5,000 字以上、附排行與統計表，每個數字標註官方來源。</p>
    <div style="font-family:var(--font-mono);font-size:12px;letter-spacing:1px;color:var(--faint);margin-top:10px">共 {len(articles)} 篇 · 最新在前</div>
  </section>
  {lead}{grid_block}
  </main>
{_bb_footer(site)}
</div>
</body>
</html>
"""


def render_sport_sitemap(articles: list, site: dict) -> str:
    base = site["base"]
    urls = [f"{base}/", f"{base}/articles/"] + [f"{base}/articles/{a['slug']}/" for a in articles]
    body = "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{body}</urlset>\n")


def _build_sport_site(articles: list, sport: str):
    """Render a non-soccer site's landing + sitemap. Articles already rendered to their out_dir
    by build(). `articles` here are that sport's articles, newest-first."""
    site = SITES.get(sport, SOCCER_SITE)
    label = {"baseball": "棒球"}.get(sport, sport)
    pub = ROOT / f"public-{sport}"
    pub.mkdir(parents=True, exist_ok=True)
    (pub / "index.html").write_text(render_sport_index(articles, site, label), encoding="utf-8")
    # 真正的文章列表頁（nav「文章」→ /articles/），與首頁區隔、文章導向，非首頁克隆
    (pub / "articles").mkdir(parents=True, exist_ok=True)
    (pub / "articles" / "index.html").write_text(
        render_sport_articles_index(articles, site, label), encoding="utf-8")
    (pub / "sitemap.xml").write_text(render_sport_sitemap(articles, site), encoding="utf-8")
    (pub / "feed.xml").write_text(render_feed(articles, site), encoding="utf-8")
    print(f"⚾ {sport} site: index + sitemap + feed ({len(articles)} articles) → {pub}/")


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
        # zero-touch backfill: existing WC articles have no `competition:` field and
        # implicitly belong to wc2026. New league articles set it explicitly.
        meta.setdefault("competition", "wc2026")
        slug = meta["slug"]

        if meta.get("type") == "daily":
            body = strip_medium_guide(body)
        body = inject_inline_images(body)
        body = strip_h1(body)

        excerpt = extract_excerpt(body)
        faq = parse_faq(body)  # mirror author-written FAQ section into FAQPage schema
        body_html = md_lib.markdown(body, extensions=["extra", "sane_lists"])

        # route to the comp's sport site: soccer -> public/articles (unchanged),
        # baseball -> public-baseball/articles. Soccer path == OUT/slug (byte-identical).
        out_dir = pub_root_for(meta) / "articles" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        # cp all non-md assets
        for asset in d.iterdir():
            if asset.is_file() and asset.suffix != ".md":
                shutil.copy2(asset, out_dir / asset.name)

        articles.append({"slug": slug, "meta": meta, "excerpt": excerpt,
                         "faq": faq, "body_html": body_html, "out_dir": out_dir})

    # ----- prev/next neighbors computed PER SITE (sport) so each site's daily/feature rails
    # are independent. Soccer's group == all WC/soccer articles, so its neighbors (and thus
    # output) stay byte-identical; baseball features never enter soccer's rail. -----
    groups = {}  # sport -> [article dicts]
    for a in articles:
        groups.setdefault(_sport_of(a["meta"]), []).append(a)

    nav_for = {}  # slug -> (prev_nav, next_nav, more_dailies, kind)
    for group in groups.values():
        dailies_asc = sorted(
            [a for a in group if a["meta"].get("type") == "daily"],
            key=lambda a: str(a["meta"].get("date", "")),
        )
        features_asc = sorted(
            [a for a in group if a["meta"].get("type") != "daily"],
            key=lambda a: (str(a["meta"].get("date", "")), a["slug"]),
        )
        recent_dailies = list(reversed(dailies_asc))[:3]
        n = len(dailies_asc)
        for i, a in enumerate(dailies_asc):
            prev_nav = dailies_asc[i - 1] if i > 0 else None        # older date → 前一日戰報
            next_nav = dailies_asc[i + 1] if i < n - 1 else None    # newer date → 後一日戰報
            skip = {a["slug"]}
            if prev_nav:
                skip.add(prev_nav["slug"])
            if next_nav:
                skip.add(next_nav["slug"])
            more = [d for d in reversed(dailies_asc) if d["slug"] not in skip][:3]
            nav_for[a["slug"]] = (prev_nav, next_nav, more, "daily")
        m = len(features_asc)
        for i, a in enumerate(features_asc):
            prev_nav = features_asc[i - 1] if i > 0 else None        # earlier feature → 前一篇
            next_nav = features_asc[i + 1] if i < m - 1 else None    # later feature → 後一篇
            nav_for[a["slug"]] = (prev_nav, next_nav, recent_dailies, "feature")

    # ----- render every article now that neighbors are known (out_dir already per-site) -----
    for a in articles:
        prev_nav, next_nav, more, kind = nav_for.get(a["slug"], (None, None, [], "daily"))
        html_out = render_article(a["meta"], a["body_html"], a["slug"], a["excerpt"],
                                  prev_nav=prev_nav, next_nav=next_nav,
                                  more_dailies=more, nav_kind=kind, faq=a["faq"])
        (a["out_dir"] / "index.html").write_text(html_out, encoding="utf-8")
        print(f"✅ {a['slug']}")

    # ----- per-site index / feed / sitemap (sort by date desc; feature > daily on tie) -----
    type_rank = {"feature": 0, "daily": 1}

    def _sorted(lst):
        return sorted(lst, key=lambda a: (str(a["meta"].get("date", "")),
                      -type_rank.get(a["meta"].get("type", "daily"), 9)), reverse=True)

    # soccer (foootball): unchanged path -> public/ (byte-identical)
    soccer_sorted = _sorted(groups.get("soccer", []))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(render_index(soccer_sorted), encoding="utf-8")
    print(f"📚 index.html ({len(soccer_sorted)} articles) → {OUT}/index.html")
    feed_path = ROOT / "public" / "feed.xml"
    feed_path.write_text(render_feed(soccer_sorted), encoding="utf-8")
    print(f"📡 feed.xml ({min(len(soccer_sorted), FEED_MAX)} items) → {feed_path}")

    # non-soccer sports (baseball.twtools.cc ...): own landing + sitemap under public-<sport>/
    for sport, group in groups.items():
        if sport == "soccer":
            continue
        _build_sport_site(_sorted(group), sport)


if __name__ == "__main__":
    build()
