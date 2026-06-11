#!/usr/bin/env python3
"""fetch-results.py — 抓 2026 世界盃已踢完比分 + 射手榜，寫回站台資料。

每日（小組賽 6/11 起）由 update-fixtures.py 呼叫：
1. 用 OpenAI gpt-5 + web_search 抓「已踢完」比賽的 final score + 目前射手榜
2. LLM 只負責填**我們給的 match_no**（deterministic，不靠隊名 fuzzy match）
3. normalize 後寫回：
   - public/fixtures-data.json → matches[].home_score / away_score（int；#2 積分 source of truth）
   - public/standings/scorers.json → 射手榜（#4）
   build-standings.py 之後讀這兩份自動算積分 + render 射手榜。

防 upstream drift（[[feedback_pipeline_upstream_output_normalize]]）：
- 只接受 int 比分、0..29 sanity range，缺/非數字一律 skip（不覆寫既有值）
- 只問 date <= today 且非 placeholder 隊（"Winner …" 等）的場次
- date-guard：today < 2026-06-11 直接 skip exit 0（開賽前無資料，省 OpenAI cost）

用法：
    python3 fetch-results.py                 # live fetch（預設）
    python3 fetch-results.py --from-file X   # 從本地 json 注入（測試用，不打 API）
    python3 fetch-results.py --dry-run       # 只 print 不寫檔

成本：~$0.10-0.20 / 次（gpt-5 + web_search），latency 3-5 min
"""

import argparse
import datetime
import importlib.util
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
FIXTURES_DATA = PUBLIC / "fixtures-data.json"
SCORERS_JSON = PUBLIC / "standings" / "scorers.json"

GROUP_START = datetime.date(2026, 6, 11)  # 小組賽開賽，results 從這天起才有意義
SANITY_MAX = 29                            # 單隊單場進球上限 sanity（史上最高 31:0 是極端，留餘裕）
PLACEHOLDER_RE = re.compile(r"\b(Winner|Runner-up|Loser|Best 3rd)\b", re.I)

# ---- 借 fetch-fixtures.py 的 load_env + call_openai_responses（單一來源）----
_spec = importlib.util.spec_from_file_location(
    "fetch_fixtures", ROOT / "scripts" / "fetch-fixtures.py"
)
ff = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ff)


# ---------------- prompt ----------------

PROMPT_HEAD = """你是足球賽果資料蒐集助手。請用 web_search 查 2026 美加墨 FIFA 世界盃**已經踢完**的比賽最終比分，以及目前的射手榜（Golden Boot race）。

權威來源（cross-check 2-3 個）：FIFA 官方 (fifa.com)、ESPN、BBC Sport、NBC Sports。

下面是賽程清單（編號 = match_no）。請**只**回傳「已經踢完、有正式最終比分」的場次，照 match_no 對應填入比分（90 分鐘 + 延長賽後的最終比分，不含 PK 大戰）：

"""

PROMPT_TAIL = """

**輸出規則（嚴格）**：只輸出一個 JSON 物件，不要任何其他文字、不要 markdown code fence：
{
  "results": [
    {"match_no": <int>, "home_score": <int>, "away_score": <int>}
  ],
  "scorers": [
    {"rank": <int>, "player": "<球員英文名>", "team_code": "<FIFA 3碼，如 BRA>", "goals": <int>, "assists": <int 可省略>}
  ]
}

- results 只放確定踢完的場次；尚未開踢或進行中的不要放
- scorers 放目前進球數 top 15（並列照進球數排序）
- 全部數字用 int，不要字串、不要 null
"""


def build_prompt(askable):
    lines = [
        f'{m["match_no"]}. {m["date"]} {m["home_team"]} vs {m["away_team"]}'
        for m in askable
    ]
    return PROMPT_HEAD + "\n".join(lines) + PROMPT_TAIL


# ---------------- parse（純函式，可測）----------------

def extract_json(text):
    """從 LLM 回傳文字抽出第一個 JSON 物件（容忍 ```json fence / 前後雜訊）。"""
    if not text:
        raise ValueError("empty response text")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        return json.loads(fence.group(1))
    # 否則抓第一個 { 到最後一個 }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in response")
    return json.loads(text[start : end + 1])


def clean_results(raw_results, valid_match_nos):
    """normalize results：只留 int 比分 + 在賽程內 + sanity range 的場次。回 dict[match_no -> (h, a)]。"""
    out = {}
    for r in raw_results or []:
        try:
            mn = int(r["match_no"])
            h = int(r["home_score"])
            a = int(r["away_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if mn not in valid_match_nos:
            continue
        if not (0 <= h <= SANITY_MAX and 0 <= a <= SANITY_MAX):
            continue
        out[mn] = (h, a)
    return out


def clean_scorers(raw_scorers):
    """normalize 射手榜：rank/goals 為 int、player 非空。"""
    out = []
    for s in raw_scorers or []:
        try:
            goals = int(s["goals"])
            player = str(s["player"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if not player or goals < 0 or goals > 60:
            continue
        out.append({
            "rank": int(s.get("rank", 0)) or None,
            "player": player,
            "team_code": str(s.get("team_code", "")).strip().upper()[:3],
            "goals": goals,
            "assists": int(s["assists"]) if isinstance(s.get("assists"), (int, str)) and str(s.get("assists")).isdigit() else None,
        })
    # 照進球數重排 + 補 rank
    out.sort(key=lambda x: -x["goals"])
    for i, s in enumerate(out):
        s["rank"] = i + 1
    return out[:15]


def apply_results(fixtures_data, results_map):
    """把 results_map 寫進 fixtures_data["matches"]。回 (updated_count, changed)。"""
    by_no = {m["match_no"]: m for m in fixtures_data["matches"]}
    updated = 0
    changed = False
    for mn, (h, a) in results_map.items():
        m = by_no.get(mn)
        if not m:
            continue
        if m.get("home_score") != h or m.get("away_score") != a:
            changed = True
        m["home_score"] = h
        m["away_score"] = a
        updated += 1
    return updated, changed


# ---------------- main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-file", help="從本地 json 注入 results/scorers（測試，不打 API）")
    ap.add_argument("--dry-run", action="store_true", help="不寫檔，只 print")
    args = ap.parse_args()

    today = datetime.date.today()
    if today < GROUP_START and not args.from_file:
        days = (GROUP_START - today).days
        print(f"📅 今天 {today} < 開賽日 {GROUP_START}（還有 {days} 天），skip results fetch")
        sys.exit(0)

    fixtures_data = json.loads(FIXTURES_DATA.read_text(encoding="utf-8"))
    matches = fixtures_data["matches"]
    valid_nos = {m["match_no"] for m in matches}

    # 取得 raw payload
    if args.from_file:
        payload = json.loads(pathlib.Path(args.from_file).read_text(encoding="utf-8"))
        print(f"🧪 from-file: {args.from_file}")
    else:
        # 只問 date <= today 且非 placeholder 隊的場次
        askable = [
            m for m in matches
            if m["date"] <= today.isoformat()
            and not PLACEHOLDER_RE.search(m["home_team"])
            and not PLACEHOLDER_RE.search(m["away_team"])
        ]
        if not askable:
            print("📭 沒有 date<=today 的可問場次，skip")
            sys.exit(0)
        print(f"📤 OpenAI fetch：問 {len(askable)} 場（date<=今天）的最終比分 + 射手榜 …")
        env = ff.load_env()
        api_key = env.get("OPENAI_API_KEY")
        model = env.get("OPENAI_MODEL", "gpt-5")
        endpoint = env.get("OPENAI_RESPONSES_ENDPOINT", "https://api.openai.com/v1/responses")
        if not api_key:
            print("❌ OPENAI_API_KEY 找不到（pipeline.env / meeting-tool/.env）")
            sys.exit(1)
        resp = ff.call_openai_responses(build_prompt(askable), model, api_key, endpoint)
        # 存 raw 供 audit（fixtures/*.raw.json 已 gitignore，不進 commit）
        if not args.dry_run:
            (ROOT / "fixtures" / "results.raw.json").write_text(
                json.dumps(resp["raw"], ensure_ascii=False, indent=1), encoding="utf-8"
            )
        payload = extract_json(resp["text"])

    results_map = clean_results(payload.get("results"), valid_nos)
    scorers = clean_scorers(payload.get("scorers"))
    updated, changed = apply_results(fixtures_data, results_map)
    print(f"✅ parse：{len(results_map)} 場有效比分（寫入 {updated}）、射手榜 {len(scorers)} 人")

    if args.dry_run:
        print("🚱 dry-run，不寫檔")
        print(json.dumps({"results": results_map, "scorers": scorers}, ensure_ascii=False, indent=1)[:800])
        return

    if updated == 0:
        print("⏭️ 0 場比分更新——fixtures-data.json 保持原樣不重寫（避免 minify 假 diff；2026-06-11）")
    else:
        FIXTURES_DATA.write_text(json.dumps(fixtures_data, ensure_ascii=False, indent=2), encoding="utf-8")
    SCORERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    SCORERS_JSON.write_text(
        json.dumps({"updated": today.isoformat(), "scorers": scorers}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"💾 寫回 fixtures-data.json（{updated} 場）+ scorers.json（{len(scorers)} 人）")


if __name__ == "__main__":
    main()
