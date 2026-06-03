#!/usr/bin/env python3
"""
update-fixtures.py — 自動 update 淘汰賽 fixtures + regen ICS + git push

每天 launchd 13:30 跑（worldcup-daily 13:03 跑完 30 min 後）：
1. fetch-fixtures.py knockout mode → 覆寫 fixtures/knockout.json + .raw.json
2. gen-ics.py → 重 regen 48 隊 ICS + tournament.ics
3. git diff 看 fixtures + public/cal/ 有沒有變動：
   - 無變動 → reset + exit 0 quiet（避免空 commit）
   - 有變動 → git add + commit + push origin main
4. CF Pages auto-deploy（~1-3 min）→ 用戶端 12-24h 內背景 sync

執行條件：
- 只在「淘汰賽抽完」期間有意義（6/28 R32 開始 - 7/19 決賽）
- 在 group stage 期間（6/11-6/27）跑也 OK，可能拿到 placeholder bracket
- A 倒數期 6/1-6/10 launchd 也可載入但無實質 update（idempotent + exit 0）

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


def run(cmd, **kwargs):
    """跑 cmd 在 REPO 目錄下；回 (returncode, stdout, stderr)"""
    kwargs.setdefault("cwd", REPO)
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **kwargs)


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main():
    log("=== update-fixtures.py start ===")

    # 0. 確認 working tree clean — 不然 abort（避免覆蓋手動編輯中的檔案）
    r = run(["git", "status", "--porcelain"])
    if r.stdout.strip():
        log(f"⚠️  working tree dirty, abort:\n{r.stdout}")
        sys.exit(1)

    # 1. fetch knockout fixtures
    log("📤 fetch-fixtures.py knockout …")
    r = run(["python3", "scripts/fetch-fixtures.py", "knockout"])
    log(r.stdout.strip())
    if r.returncode != 0:
        log(f"❌ fetch-fixtures.py 失敗: {r.stderr}")
        sys.exit(1)

    # 2. regen ICS
    log("🛠️  gen-ics.py …")
    r = run(["python3", "scripts/gen-ics.py"])
    log(r.stdout.strip())
    if r.returncode != 0:
        log(f"❌ gen-ics.py 失敗: {r.stderr}")
        sys.exit(1)

    # 3. diff 看有沒有變動（stage 之後 diff --cached）
    run(["git", "add", "fixtures/knockout.json", "public/cal/", "public/fixtures-data.js", "public/fixtures-data.json"])
    r = run(["git", "diff", "--cached", "--quiet"])
    if r.returncode == 0:
        log("✅ 無變動，reset + exit")
        run(["git", "reset", "HEAD", "--", "fixtures/", "public/"])
        # restore working tree（避免本機留下 stale 變動）
        run(["git", "checkout", "--", "fixtures/knockout.json", "public/cal/", "public/fixtures-data.js", "public/fixtures-data.json"])
        log("=== update-fixtures.py end (no-op) ===")
        sys.exit(0)

    # 4. 有變動 → commit + push
    date_str = datetime.date.today().isoformat()
    commit_msg = f"""chore(auto): update knockout fixtures {date_str}

自動 trigger by launchd 13:30 cron (com.charlie.foootball-tools-update.plist).

來源：fetch-fixtures.py knockout (OpenAI gpt-5 + web_search)
ICS regen：gen-ics.py 覆寫 public/cal/*.ics + tournament.ics

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
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
