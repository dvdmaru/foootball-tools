# foootball-tools

@foootball Medium account 的延伸工具集，主站掛在 `foootball.twtools.cc`（Cloudflare Pages + Cloudflare DNS CNAME）。

第一個工具：**2026 美加墨世界盃賽程行事曆**

## 工具列表

| 工具 | 路徑 | 狀態 |
|---|---|---|
| **2026 世界盃賽程行事曆** | `/` | Phase 0 雛形（48 隊 ICS + 國旗 grid） |
| 每日賽程社群圖文 | `/daily-schedule/` | TODO（整合 worldcup-daily pipeline） |
| 球隊賽程 PNG 對戰表 ×48 | `/teams/` | TODO |

## 用戶 UX：訂閱 / 下載 / 加入 Google Calendar

每支球隊三軌按鈕：

1. **`webcal://` 訂閱**（推薦）
   - Apple Calendar (iOS / macOS)：點擊一鍵跳「新增訂閱」對話框，淘汰賽抽完 ICS 更新後自動 sync
   - Google Calendar (桌機)：複製 URL 貼到 Settings → Add calendar → From URL；mobile auto sync
2. **下載 `.ics`**（單次匯入）
   - 跨平台 work，但更新要重抓
3. **加入 Google Calendar（單場 event）**
   - 每場附 `https://calendar.google.com/calendar/render?action=TEMPLATE&...` deep link，一鍵加單場

## 開發

```bash
# 抓 group stage fixtures (gpt-5 + web_search，~$0.25 / 次)
python3 scripts/fetch-fixtures.py group-stage

# 抓 knockout placeholder (group stage 結束後對戰才會 fill 上)
python3 scripts/fetch-fixtures.py knockout

# 生 48 隊 ICS + tournament.ics
python3 scripts/gen-ics.py

# 本機預覽
open public/index.html
```

## 自動 update pipeline (淘汰賽期間 6/28-7/19)

`scripts/update-fixtures.py` 每天 launchd 13:33 自動跑：

```
13:03  worldcup-daily 跑 daily 戰報
13:33  foootball-tools update-fixtures.py
       ├─ date guard: < 2026-06-28 → skip & exit (group stage 期間 placeholder noise)
       ├─ 6/28+ : fetch-fixtures.py knockout (gpt-5+search)
       ├─        gen-ics.py 重 regen 48 隊 ICS + tournament.ics
       ├─        git diff 看有沒有實質變動
       └─        有 → commit + push origin main → CF Pages auto-deploy
（用戶端日曆 app 12-24h 內背景 sync 拿到新版 ICS）
```

每天 ~$0.20-0.30 OpenAI fetch cost（6/28-7/19 共 ~22 天 = ~$5），加 worldcup-daily 已有 $13/月 = 兩個專案 ~$23/月。

### 安裝 launchd

```bash
cp ~/Github-Repo/foootball-tools/com.charlie.foootball-tools-update.plist \
   ~/Library/LaunchAgents/

launchctl load ~/Library/LaunchAgents/com.charlie.foootball-tools-update.plist
launchctl list | grep foootball-tools-update    # 確認 status 0
```

Logs：
- stdout: `/tmp/foootball-tools-update.stdout.log`
- stderr: `/tmp/foootball-tools-update.stderr.log`

手動跑（debug 或 6/28+ 想立刻 trigger 一次）：

```bash
python3 ~/Github-Repo/foootball-tools/scripts/update-fixtures.py
```

## 部署

Cloudflare Pages：
- repo: `dvdmaru/foootball-tools`
- production branch: `main`
- build command: `python3 scripts/gen-ics.py`（或 build-on-push）
- output dir: `public`
- custom domain: `foootball.twtools.cc`

DNS：CF DNS 加 CNAME `foootball.twtools.cc` → `<project>.pages.dev`（細節見 [[feedback-cf-pages-custom-domain]]）

## 結構

```
foootball-tools/
├── README.md
├── .gitignore
├── fixtures/           # 賽程 source-of-truth JSON
│   ├── group-stage.json
│   └── knockout.json   # 抽完後 fill in
├── scripts/            # build scripts
│   ├── fetch-fixtures.py
│   └── gen-ics.py
├── templates/          # HTML template (Phase 1 圖文)
└── public/             # CF Pages serve root
    ├── index.html
    ├── cal/            # 48 隊 ICS + tournament.ics
    │   ├── POR.ics
    │   ├── BRA.ics
    │   └── ...
    └── teams/          # Phase 1：每隊一頁
```
