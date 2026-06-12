#!/usr/bin/env python3
"""
update-fixtures.py — 戰況數據每日 orchestrator（比分 + 射手榜 + 淘汰賽）+ git push

每天 launchd 6:00 / 12:30 / 14:30 跑（增量；多數日中午前就更新完，中午開球場滑到 14:30），date-gated：
1. fetch-results.py（6/11 起）→ Claude headless 主抓已踢完比分 + 射手榜（零 API 費），
   寫回 fixtures-data.json + scorers.json；14:30 那次加 --cross-check（OpenAI 獨立複查、不一致推 LINE）
2. fetch-fixtures.py knockout + gen-ics.py（6/28 起）→ 淘汰賽真隊 + 重生 ICS
3. build-standings.py → 重生 /standings/（積分自動算 from 比分 + 射手榜 + bracket）
4. git diff fixtures/ + public/（results.raw.json 已 gitignore）：
   - 無變動 → reset + restore + exit 0 quiet（避免空 commit）
   - 有變動 → git add + commit + push origin main
5. CF auto-deploy（~1-3 min）→ 訂閱用戶端 12-24h 內背景 sync

執行條件（date guard）：
- < 6/11 開賽前：整條 no-op exit 0（無資料，省 OpenAI cost）
- 6/11-6/27 小組賽：跑 results + 射手榜 + standings
- 6/28-7/19 淘汰賽：加跑 knockout fetch + ICS regen

Logs:
- stdout / stderr 由 launchd 寫到 /tmp/foootball-tools-update.{stdout,stderr}.log
- 每次跑 append datestamp 行
"""

import datetime
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path("/Users/charlie.chien/Github-Repo/foootball-tools")
COMMIT_MSG_TMP = pathlib.Path("/tmp/foootball-tools-commit-msg.txt")
PY = sys.executable  # launchd 下裸 "python3" 會掉到沒裝 markdown 的系統 python；用同一支 interpreter spawn 子腳本


def run(cmd, **kwargs):
    """跑 cmd 在 REPO 目錄下；回 (returncode, stdout, stderr)"""
    kwargs.setdefault("cwd", REPO)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


GROUP_START = datetime.date(2026, 6, 11)      # 小組賽開賽 → results fetch（比分 + 射手榜）從這天起
KNOCKOUT_START = datetime.date(2026, 6, 28)   # R32 first match → knockout fetch 從這天起


def step(label, cmd, fatal=True):
    """跑一個 pipeline step，log 結果。fatal=False 時失敗只 warn 不 abort。回 returncode。"""
    log(f"▶ {label} …")
    r = run(cmd)
    if r.stdout.strip():
        log(r.stdout.strip())
    if r.returncode != 0:
        log(f"{'❌' if fatal else '⚠️'} {label} 失敗: {r.stderr.strip()[:3000]}")
        if fatal:
            sys.exit(1)
    return r.returncode


def main():
    log("=== update-fixtures.py start ===")

    # Date guard：開賽前（< 6/11）整條 no-op
    # 理由：開賽前沒有任何比分/射手榜資料，knockout 也是 placeholder；跑也只是浪費 OpenAI cost + 假 commit。
    today = datetime.date.today()
    if today < GROUP_START:
        days = (GROUP_START - today).days
        log(f"📅 今天 {today} < 開賽日 {GROUP_START}（還有 {days} 天），skip（no-op）")
        log("=== update-fixtures.py end (pre-tournament, no-op) ===")
        sys.exit(0)

    # 0. 確認 working tree clean — 不然 abort（避免覆蓋手動編輯中的檔案）
    r = run(["git", "status", "--porcelain"])
    if r.stdout.strip():
        log(f"⚠️  working tree dirty, abort:\n{r.stdout}")
        sys.exit(1)

    # 1. fetch results（小組賽比分 + 射手榜）— 6/11 起每天，6:00 / 12:30 / 14:30 增量
    #    主抓 = Claude headless（零 API 費）；下午那次（hour>=14）加 --cross-check 用 OpenAI 獨立複查。
    #    fetch-results.py 內部也有 date-guard；fetch 失敗不 abort 整條（仍可用既有資料 rebuild）。
    cross = datetime.datetime.now().hour >= 14   # 14:30 那次跑 cross-check（6:00 / 12:30 純主抓）
    fetch_cmd = [PY, "scripts/fetch-results.py"] + (["--cross-check"] if cross else [])
    step(f"fetch-results.py（比分 + 射手榜{'｜+OpenAI cross-check' if cross else ''}）",
         fetch_cmd, fatal=False)

    # 2. knockout fetch + ICS regen — 6/28 起（淘汰賽抽完後才有實質真隊）
    if today >= KNOCKOUT_START:
        step("fetch-fixtures.py knockout", [PY, "scripts/fetch-fixtures.py", "knockout"])
        step("gen-ics.py（重生 ICS）", [PY, "scripts/gen-ics.py"])

    # 3. rebuild 戰況中心（積分 from 比分 + 射手榜 + bracket）
    step("build-standings.py（戰況中心）", [PY, "scripts/build-standings.py"])

    # 4. diff 看有沒有變動（results.raw.json 已 .gitignore，不進 commit）
    run(["git", "add", "fixtures/", "public/"])
    r = run(["git", "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        log("✅ 無變動，reset + restore + exit")
        run(["git", "reset", "HEAD", "--", "fixtures/", "public/"])
        run(["git", "checkout", "--", "fixtures/", "public/"])
        log("=== update-fixtures.py end (no-op) ===")
        sys.exit(0)

    # 5. 有變動 → commit + push
    date_str = today.isoformat()
    phase = "knockout + 比分" if today >= KNOCKOUT_START else "小組賽比分 + 射手榜"
    commit_msg = f"""chore(auto): update {phase} {date_str}

自動 trigger by launchd 6:00/12:30/14:30 cron (com.charlie.foootball-tools-update.plist).

來源：fetch-results.py（比分 + 射手榜，Claude headless 主抓 + WebSearch；14:30 OpenAI cross-check）
{"+ fetch-fixtures.py knockout + gen-ics.py（ICS regen）" if today >= KNOCKOUT_START else ""}
戰況中心 rebuild：build-standings.py（積分自動算 + 射手榜 + bracket）

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
"""
    COMMIT_MSG_TMP.write_text(commit_msg, encoding="utf-8")

    log("📝 git commit …")
    r = run([
        "git",
        "-c", "user.email=charlie.chien@gmail.com",
        "-c", "user.name=Charlie Chien (auto)",
        "commit",
        "-F", str(COMMIT_MSG_TMP),
    ])
    log(r.stdout.strip())
    if r.returncode != 0:
        log(f"❌ commit 失敗: {r.stderr}")
        sys.exit(1)

    log("⬆️  git push origin main …")
    r = run(["git", "push", "origin", "main"])
    log(r.stdout.strip() + r.stderr.strip())
    if r.returncode != 0:
        log(f"❌ push 失敗: {r.stderr}")
        sys.exit(1)

    log("✅ 完成 — CF Pages auto-deploy 約 1-3 min")
    log("=== update-fixtures.py end (pushed) ===")


if __name__ == "__main__":
    main()
