#!/usr/bin/env python3
"""
fetch-fixtures.py — 用 OpenAI gpt-5 + web_search 抓 2026 美加墨世界盃完整賽程。

第一次 (group stage)：抓 12 組 × 6 場 = 72 場 group stage。
淘汰賽：抽完之後再跑同 script (mode=knockout) 抓 32 場淘汰。

借用 worldcup-daily/prepare-daily.py 同樣的 OpenAI Responses API + web_search_preview pattern。

用法：
    python3 fetch-fixtures.py [group-stage|knockout]
    # 預設 group-stage

成本：~$0.20-0.30 / 次，latency 4-6 min
輸出：fixtures/group-stage.json 或 fixtures/knockout.json
"""

import datetime
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORLDCUP_DAILY = pathlib.Path("/Users/charlie.chien/Library/CloudStorage/Dropbox/AI/CoWork/worldcup-daily")

ENV_FILES = [
    WORLDCUP_DAILY / "pipeline.env",
    WORLDCUP_DAILY.parent / "meeting-tool" / ".env",
]


def load_env() -> dict:
    env = {}
    for f in ENV_FILES:
        if not f.exists():
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def call_openai_responses(prompt: str, model: str, api_key: str, endpoint: str) -> dict:
    body = json.dumps({
        "model": model,
        "tools": [{"type": "web_search_preview"}],
        "input": prompt,
    }, ensure_ascii=False)

    result = subprocess.run(
        [
            "curl", "-sS", "--fail-with-body", "--max-time", "600",
            "-X", "POST", endpoint,
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "Content-Type: application/json",
            "--data-binary", "@-",
        ],
        input=body.encode("utf-8"),
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl failed: {result.stderr.decode()[:500]}")

    response = json.loads(result.stdout)
    output_text = response.get("output_text", "")
    if not output_text:
        for item in response.get("output", []):
            if item.get("type") == "message":
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        output_text += c.get("text", "")

    return {"text": output_text, "raw": response}


GROUP_STAGE_PROMPT = """你是足球賽程資料蒐集助手。請用 web_search 搜尋並列出 2026 美加墨 FIFA 世界盃 group stage（小組賽）完整賽程。

**範圍**：12 組（A 到 L），每組 6 場，共 **72 場**。日期範圍 2026-06-11 至 2026-06-27。

**權威來源**（請至少參考 2-3 個 cross-check）：
- FIFA 官方 (fifa.com)
- ESPN
- NBC Sports
- Wikipedia "2026 FIFA World Cup"

**回傳 strict JSON array**，每場一個 object：

```json
{
  "match_no": 1,
  "date": "2026-06-11",
  "kickoff_et": "20:00",
  "kickoff_taipei": "08:00+1",
  "stadium": "Estadio Azteca",
  "city": "Mexico City",
  "country_host": "MEX",
  "group": "A",
  "home_team": "Mexico",
  "home_iso": "mx",
  "home_code": "MEX",
  "away_team": "South Africa",
  "away_iso": "za",
  "away_code": "RSA"
}
```

**欄位規格**：
- `match_no`: 1-72，按官方編號
- `date`: YYYY-MM-DD（美加墨當地日期）
- `kickoff_et`: ET 時間 24h "HH:MM"（東岸時間 UTC-4 EDT）
- `kickoff_taipei`: 台北時間 24h "HH:MM"，如過午則加 "+1" 或 "+2" 表示隔天 / 後天
- `stadium`: 場館全名
- `city`: 城市
- `country_host`: 主辦國 ISO3 代碼（USA / CAN / MEX）
- `group`: 組別 "A" 到 "L"
- `home_team` / `away_team`: 國家名（英文）
- `home_iso` / `away_iso`: 兩字母 ISO 國碼（小寫，flagcdn.com 用）
- `home_code` / `away_code`: FIFA 3 字母代碼（大寫）

**重要**：
1. 一定要 72 場全列，缺一場都不行
2. 台北時間換算 = ET +12h（夏令）；過午要標 "+1"
3. 主隊 / 客隊定義按官方賽程，不要自作主張
4. **只回傳 JSON array，不要任何 markdown、prose、explanation**。從 `[` 開始到 `]` 結束。

開始搜尋並輸出 JSON。
"""


KNOCKOUT_PROMPT = """你是足球賽程資料蒐集助手。請用 web_search 搜尋並列出 2026 美加墨 FIFA 世界盃淘汰賽完整賽程。

**範圍**：32 場淘汰賽：
- Round of 32 (16 場) — 6/28 至 7/3
- Round of 16 (8 場) — 7/4 至 7/7
- Quarter-finals (4 場) — 7/9 至 7/11
- Semi-finals (2 場) — 7/14 至 7/15
- 3rd place play-off (1 場) — 7/18
- Final (1 場) — 7/19

每場欄位同 group-stage JSON 結構，但加上：
- `round`: "R32" / "R16" / "QF" / "SF" / "3rd" / "Final"
- `home_team`: 若還未抽完，寫對戰路徑 e.g. "Winner Group A" 或 "Winner Match 73"
- `away_team`: 同上

回傳 strict JSON array，從 `[` 到 `]`，不要 markdown / prose。
"""


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "group-stage"
    if mode not in ("group-stage", "knockout"):
        print(f"❌ unknown mode '{mode}', use 'group-stage' or 'knockout'", file=sys.stderr)
        sys.exit(1)

    env = load_env()
    if not env.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 找不到（檢查 worldcup-daily/pipeline.env 或 meeting-tool/.env）", file=sys.stderr)
        sys.exit(1)

    prompt = GROUP_STAGE_PROMPT if mode == "group-stage" else KNOCKOUT_PROMPT
    output_path = ROOT / "fixtures" / f"{mode}.json"
    raw_path = ROOT / "fixtures" / f"{mode}.raw.json"

    print(f"📤 Calling OpenAI {env.get('OPENAI_MODEL', 'gpt-5')} + web_search …  (估 4-6 min, ~$0.20-0.30)")

    result = call_openai_responses(
        prompt,
        model=env.get("OPENAI_MODEL", "gpt-5"),
        api_key=env["OPENAI_API_KEY"],
        endpoint=env.get("OPENAI_RESPONSES_ENDPOINT", "https://api.openai.com/v1/responses"),
    )

    raw_path.write_text(json.dumps(result["raw"], indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"📥 raw response → {raw_path}")

    text = result["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0].strip()

    try:
        fixtures = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse failed: {e}", file=sys.stderr)
        print(f"   raw text 開頭 500 chars: {text[:500]}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(fixtures, list):
        print(f"❌ 回傳不是 array: {type(fixtures)}", file=sys.stderr)
        sys.exit(1)

    expected_count = 72 if mode == "group-stage" else 32
    if len(fixtures) != expected_count:
        print(f"⚠️  收到 {len(fixtures)} 場，預期 {expected_count} 場 — 檢查 raw.json", file=sys.stderr)

    output_path.write_text(json.dumps(fixtures, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {len(fixtures)} 場 → {output_path}")


if __name__ == "__main__":
    main()
