#!/usr/bin/env python3
"""claude_fetch.py — headless Claude Code + WebSearch fetch helper（走 Max 訂閱額度，零 API 費）。

戰況 pipeline（fetch-results.py）的**主抓** backend。技術同 worldcup-daily/prepare-daily.py
的 Plan B（call_claude_headless），但刻意自成一份留在本 repo 內，**不讓 launchd job 依賴
Dropbox 路徑 / sync 狀態**（可靠性）；兩條 pipeline 共用「同一套技術」而非同一個檔。
OpenAI 僅在 14:30 那次當 cross-check（見 fetch-results.py --cross-check）。
"""

import subprocess

CLAUDE_BIN = "/Users/charlie.chien/.local/bin/claude"


def call_claude_headless(prompt: str, model: str = "sonnet", timeout: int = 900) -> dict:
    """headless Claude + WebSearch。回 {"text": stdout, "raw": None}。

    輸出尾巴強制純 JSON（headless Claude 常帶前言 / Sources 清單 / code fence，
    呼叫端再用 robust 解析切出 JSON 本體）。
    """
    prompt = prompt + (
        "\n\n（輸出規則：直接輸出純 JSON 本體，不要任何前言、說明文字或 "
        "Sources 來源清單、不要 markdown code fence。）"
    )
    result = subprocess.run(
        [CLAUDE_BIN, "-p", prompt, "--allowedTools", "WebSearch", "--model", model],
        capture_output=True, timeout=timeout, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude headless failed (rc={result.returncode}): {result.stderr[:300]}"
        )
    return {"text": result.stdout, "raw": None}
