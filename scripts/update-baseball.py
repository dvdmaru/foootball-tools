#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""update-baseball.py — baseball.twtools.cc 每日自動重建編排器(dashboard living-page）。

把「抓資料 → 重生頁面 →(可選)部署」串成一個指令，供 launchd 每日跑（見
scripts/com.charlie.baseball-tools-update.plist）。MLB／NPB／KBO 每日自動新鮮；CPBL 是人工
快照、本腳本不碰（過期由頁面 as-of/stale badge 誠實呈現）。

跑序鐵則（[[feedback_pipeline_upstream_output_normalize]] / sitemap 覆寫坑）：
  1. 抓資料：MLB leaders + MLB today slate + NPB games + KBO games
  2. gen-baseball-standings：先產 leagues/mlb-standings-<season>.json（首頁戰績速覽要讀）
  3. build-articles：首頁 dashboard 讀上面所有快照 + 整個覆寫 sitemap
  4. 各 generator re-merge 自己的 sitemap path（teams / standings / cpbl / data-hub）
  5.（可選）wrangler deploy

部署需非互動憑證：設環境變數 CLOUDFLARE_API_TOKEN（launchd 無法跑互動 wrangler login）。
未設 token 且未加 --deploy 時只重建、不部署（手動再 `npx wrangler deploy -c wrangler-baseball.jsonc`）。

用法：
  python3 scripts/update-baseball.py                 # 重建，不部署
  python3 scripts/update-baseball.py --deploy        # 重建 + wrangler deploy
  python3 scripts/update-baseball.py --season 2026 --date 2026-06-30
"""
import argparse
import datetime
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable  # launchd 子腳本一律用同一個 interpreter（[[feedback_launchd_subprocess_sys_executable]]）


def run(args, label):
    print(f"\n▶ {label}: {' '.join(str(a) for a in args)}", flush=True)
    r = subprocess.run(args, cwd=str(ROOT))
    if r.returncode != 0:
        print(f"  ⚠️  {label} exit={r.returncode}（繼續，避免一步壞全停；檢查上面日誌）", flush=True)
    return r.returncode


def script(name, *extra):
    return [PY, str(ROOT / "scripts" / name), *extra]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="today reference for MLB slate（預設今天）")
    ap.add_argument("--deploy", action="store_true", help="重建後跑 wrangler deploy")
    args = ap.parse_args()
    s = str(args.season)

    print(f"⚾ update-baseball · season={s} · date={args.date} · deploy={args.deploy}")

    # 1. 抓資料（MLB 官方 StatsAPI 免金鑰；NPB/KBO 走 api-baseball；CPBL 人工快照不碰）
    run(script("fetch-mlb-players.py", "leaders", "--season", s), "fetch MLB leaders")
    run(script("fetch-mlb-players.py", "today", "--date", args.date), "fetch MLB today slate")
    run(script("fetch-baseball.py", "npb"), "fetch NPB")
    run(script("fetch-baseball.py", "kbo"), "fetch KBO")

    # 2. 先產 MLB standings 快照（首頁戰績速覽要讀 leagues/mlb-standings-<season>.json）
    run(script("gen-baseball-standings.py", "--season", s), "gen standings (data)")

    # 3. 首頁 dashboard + base sitemap（必須在各 generator 之前；會整個覆寫 sitemap）
    run(script("build-articles.py"), "build-articles (homepage + sitemap)")

    # 4. 各 generator re-merge 自己的 sitemap path
    run(script("gen-baseball-team-pages.py", "--season", s), "gen team pages")
    run(script("gen-baseball-standings.py", "--season", s), "gen standings (re-merge)")
    run(script("gen-cpbl-standings.py"), "gen CPBL")
    run(script("gen-baseball-data-hub.py"), "gen data hub")

    # 5.（可選）部署
    if args.deploy or os.environ.get("CLOUDFLARE_API_TOKEN"):
        run(["npx", "wrangler", "deploy", "-c", "wrangler-baseball.jsonc"], "wrangler deploy")
    else:
        print("\n⏭  未 --deploy 且無 CLOUDFLARE_API_TOKEN → 只重建未部署。"
              "手動部署：npx wrangler deploy -c wrangler-baseball.jsonc")

    print("\n✅ update-baseball done")


if __name__ == "__main__":
    main()
