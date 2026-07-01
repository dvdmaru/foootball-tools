# Layer 2 任務 spec — CPBL 週更 + 發前 cross-check（Sonnet 5 · CoWork Schedule）

baseball.twtools.cc 每日自動更新的**混合方案第二層**。第一層（Layer 1）是本機 launchd
每日 12:00 跑 `scripts/update-baseball.py --deploy`，機械刷新 MLB（官方 StatsAPI）+ NPB/KBO
（api-baseball）、零 API 費、deterministic，見 `scripts/com.charlie.baseball-tools-update.plist`。

**Layer 2 只做腳本做不到的「判斷題」**：CPBL 無穩定公開 API（`fetch-baseball.py` 的
`/standings` 對棒球 results=0，是死路），戰績＋TOP5 只能爬 cpbl.com.tw 官方首頁人工整理；
外加發前 fact cross-check。這兩塊需要 LLM 判斷，故用 Sonnet 5 排程跑。

---

## 執行前提（硬需求，缺一不可）

- **必須在本機跑**（Claude Desktop / CoWork 本機排程，**不能是 claude.ai 雲端**）——要直接碰
  repo、python 3.13、wrangler、CF 憑證。雲端排程碰不到這些，此路不通。
- **Repo**：`/Users/charlie.chien/Github-Repo/foootball-tools`（主 checkout，**須 PR#2 已併 main**，
  否則 `update-baseball.py`/gen 腳本/`config/draft-exclude.json` 不在該 checkout 上）。
- **CF 憑證**：環境變數 `CLOUDFLARE_API_TOKEN` = **charlie.chien2019@gmail.com** 帳號、含
  Workers Scripts:Edit 的 token（worker `baseball-tools` 在 account `2f123fdee05d453c8a077b6ba541c45d`；
  ⚠️ 別誤用 charlie.chien@gmail.com，那個帳號沒權限）。
- **Python**：`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`（裸 python3 可能缺 markdown 套件）。
- **api-baseball key**：`API_FOOTBALL_KEY`（`update-baseball.py` 內部腳本自行讀
  `~/Library/CloudStorage/Dropbox/AI/CoWork/meeting-tool/.env`）。
- **模型**：Sonnet 5。
- **建議頻率**：每週一次（CPBL 半季戰績變化比 MLB 慢，且 LLM 有成本）。建議週一 12:30，
  接在 Layer 1 每日刷新之後。可自行調整。

---

## 任務指令（貼進 CoWork Schedule 的 task prompt）

> 你是 baseball.twtools.cc 的 CPBL 資料維護 agent。目標：把 CPBL 官方最新戰績＋TOP5 抓下來、
> 產出符合站上 schema 的快照、做獨立 cross-check，通過後重建並部署上線，最後回報。全程誠實、寧缺勿假。

**Step 1 — 抓 CPBL 官方資料（cpbl.com.tw）**
- 抓官方首頁／戰績頁，取得：① 6 隊戰績（排名、出賽、勝、敗、和、勝率、勝差、近況連勝/連敗）；
  ② 打擊 TOP5：打擊率 / 安打 / 全壘打 / 打點 / 盜壘；③ 投手 TOP5：防禦率 / 勝投 / 救援成功 /
  中繼成功 / 奪三振；④ 目前 `season_phase`（上半季／下半季）。
- **只記錄頁面上真實存在的數字**。抓不到的欄位留 `null`，**絕不臆測或延用舊值**（防捏造：
  event-time + entity guard）。球隊只能是 CPBL 現行 6 隊；球員名須與官方頁一致。

**Step 2 — 產新快照** `leagues/cpbl-standings-leaders-<today>.json`
- 嚴格對齊下方「快照 schema」（`gen-cpbl-standings.py` 與首頁 dashboard 都讀這些欄位）。
- `asof_taipei_date` = 今天（台北）；`fetched_at_taipei` = 現在 ISO8601 `+08:00`。
- `team_id` / `player_id` 若能從上一份快照（`leagues/cpbl-standings-leaders-*.json` 最新）對映到
  同名球隊/球員就沿用，對不到就留空——不要亂編 id。

**Step 3 — 獨立 cross-check（QA 用獨立來源，不可拿 Step 1 同一次抓取自我驗證）**
- 戰績內部一致性：每隊 `wins + losses + ties == games`；`winning_percentage ≈ wins/(wins+losses)`
  （四捨五入到小數 3 位）；排名依勝率遞減；`games_behind` 隨排名單調不減。
- 對照第二來源（例如官方「戰績」分頁 vs 首頁，或另一權威站）複核 6 隊勝敗數；不一致→**不部署**、回報差異。
- TOP5 合理區間 sanity：打擊率 .150–.400、ERA 0–9.99、全壘打/盜壘非負整數。
- entity guard：任何球隊名不在現行 6 隊、或球員/球隊對不上上一份快照的已知名單 → 標記存疑、回報。
- 與上一份快照 diff：若數字「完全沒變」或「變動離譜（單週勝場 +10）」→ 疑似抓錯，先 hold + 回報，別部署。

**Step 4 — 重建 + 部署（通過 cross-check 才做）**
- 新快照寫好後，直接跑：
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 scripts/update-baseball.py --deploy`
  （它會 build-articles → 各 generator re-merge → `wrangler deploy -c wrangler-baseball.jsonc`；
  `gen-cpbl-standings.py` 自動取檔名日期最新的快照，首頁 CPBL tab 也一起更新）。
- **provenance commit（只加這一個新檔，additive、低風險）**：
  `git add leagues/cpbl-standings-leaders-<today>.json && git commit`（訊息：
  `data(cpbl): 官方首頁快照 <today>（Layer 2 週更）`）。
  重建出的 `public-baseball/**` 屬 living output，**維持不 commit**（與 Layer 1 一致）。

**Step 5 —（選配）發前 fact cross-check pending 文章**
- 若 `config/draft-exclude.json` 的 `exclude` 有 slug（別人未審完的稿），對每篇跑
  `check-facts.py verify-standings` / `matchup-check` / `numbers-in-facts` 產報告。
- **只回報、不自動發布**：發布＝把 slug 從 `draft-exclude.json` 移除，這是人的決定
  （尊重原作者，不擅自替別人上稿）。把 cross-check 結果附在回報裡給 Charlie 判斷。

**Step 6 — 回報（成功或失敗都要報）**
- 摘要：CPBL as-of 日、6 隊勝敗變化、TOP5 有無異動、cross-check 結果（過/存疑項）、
  部署 version（wrangler 回的）、pending 文章 cross-check 結論（若跑）。
- 任一步失敗（抓取失敗 / cross-check 不過 / 部署 auth 錯）→ **不硬闖**，把錯誤與已完成到哪一步報清楚。

---

## 快照 schema（必嚴格對齊，欄位名不可改）

```jsonc
{
  "_type": "cpbl-standings-leaders",
  "league": "CPBL", "league_zh": "中華職棒",
  "season": 2026, "season_phase": "上半季",          // 上半季 / 下半季
  "asof_taipei_date": "2026-07-07",                   // 抓取日（台北）
  "fetched_at_taipei": "2026-07-07T12:34:00+08:00",
  "source": "cpbl.com.tw 官方首頁", "api_assessment": "無穩定公開 API，人工快照",
  "standings": [                                       // 6 隊，依勝率排名
    { "rank": 1, "team_id": "AAA011", "team": "味全龍",
      "games": 58, "wins": 38, "losses": 20, "ties": 0,
      "winning_percentage": "0.655",                   // 字串，小數 3 位
      "games_behind": null,                            // 第一名 null；其餘字串如 "3.5"
      "streak": "敗2" }                                // 連勝/連敗，如 "勝3"/"敗2"
    // ... 其餘 5 隊
  ],
  "leaders": {
    "batting": {                                       // key 順序 = 站上呈現序
      "batting_average": { "label_zh": "打擊率",
        "rows": [ { "rank": 1, "player_id": "0000006888", "player": "張育成",
                    "team_id": "AEO011", "team": "富邦悍將", "value": "0.331" } /* 5 rows */ ] },
      "hits":        { "label_zh": "安打",   "rows": [ /* 5 */ ] },
      "home_runs":   { "label_zh": "全壘打", "rows": [ /* 5 */ ] },
      "runs_batted_in": { "label_zh": "打點", "rows": [ /* 5 */ ] },
      "stolen_bases":{ "label_zh": "盜壘",   "rows": [ /* 5 */ ] }
    },
    "pitching": {
      "era":     { "label_zh": "防禦率",   "rows": [ /* 5 */ ] },
      "wins":    { "label_zh": "勝投",     "rows": [ /* 5 */ ] },
      "saves":   { "label_zh": "救援成功", "rows": [ /* 5 */ ] },
      "holds":   { "label_zh": "中繼成功", "rows": [ /* 5 */ ] },
      "strikeouts": { "label_zh": "奪三振", "rows": [ /* 5 */ ] }
    }
  }
}
```

`value` 一律字串（保留小數位/前導 0，如 `"0.331"`、`"2.15"`）。各榜只列官方首頁公布的 TOP5，非完整榜。

---

## 護欄（紅線，違反即中止）

- **不捏造**：只寫頁面真實有的數字；抓不到留 null；未發生的賽果不預填。
- **誠實 as-of**：`asof_taipei_date` 必為真實抓取日；頁面已內建「非官方／非即時／人工快照」警語，勿移除。
- **非官方站定位**：不放隊徽/聯盟標誌/球員照；球隊名稱權利屬 CPBL 及各權利人。
- **soccer 零污染**：絕不動 `public/`（soccer 輸出逐 byte 不變是硬合約）；此任務只碰 baseball。
- **不擅自替別人上稿**：pending 文章只 cross-check + 回報，發布（移出 draft-exclude）交人決定。
- **cross-check 不過就不部署**：寧可 hold 一週 + 回報，也不推可疑數字上線。

---

## 相關檔案 / 記憶

- Layer 1：`scripts/update-baseball.py`、`scripts/com.charlie.baseball-tools-update.plist`
- CPBL 頁生成：`scripts/gen-cpbl-standings.py`（讀 `leagues/cpbl-standings-leaders-*.json` 最新）
- 草稿 gate：`config/draft-exclude.json`（見 build-articles.py draft 排除）
- cross-check：`scripts/check-facts.py`（verify-standings / matchup-check / numbers-in-facts）
