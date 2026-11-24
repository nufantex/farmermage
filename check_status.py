"""逐一造訪型農本色電子期刊網址（Vol.54 + Vol.53），回報「連線是否成功」與「瀏覽次數」。

用法：
    pip install -r requirements.txt
    python check_status.py

注意：
- 為避免觸發網站高並發限制，同時最多僅開啟 2 條連線（Vol.54 與 Vol.53 各 1 條），
  各期內部仍維持「一次一個、間隔 0.5 秒」逐頁檢查。
- 瀏覽次數是「各期獨立、整期共用」的計數器，不是每篇各自計算；
  每造訪同一期的任何一頁都 +1，因此 Vol.54（13 頁）與 Vol.53（13 頁）會各自遞增。
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

ISSUES: dict[str, list[str]] = {
    "Vol.54": [
        "https://www.kaofarmers.tw/farmer-colours/epaper/current-issue",
        *[f"https://www.kaofarmers.tw/farmer-colours/epaper/66/{n}" for n in range(560, 572)],
    ],
    "Vol.53": [
        "https://www.kaofarmers.tw/farmer-colours/epaper/65",
        *[f"https://www.kaofarmers.tw/farmer-colours/epaper/65/{n}" for n in range(548, 560)],
    ],
}
URLS = [url for urls in ISSUES.values() for url in urls]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )
}
TIMEOUT = 15
DELAY = 0.5
RETRIES = 2

HISTORY_HEADER = ["台灣時間", "觸發方式", "連線成功", "網址總數", "本期瀏覽次數", "失敗網址", "Vol.53瀏覽次數"]

# 實測原始 HTML：<span class="py-3 text-secondary"><i class="fas fa-eye"></i>14603次</span>
VIEW_RE = re.compile(r'fa-eye"\s*>\s*</i>\s*([\d,]+)\s*次')
VIEW_RE_FALLBACK = re.compile(r">\s*([\d,]+)\s*次\s*<")


def extract_views(html: str) -> int | None:
    m = VIEW_RE.search(html)
    if not m:  # 網站改版、眼睛圖示不見時的備援：從分享區塊之後找第一個「數字+次」
        start = html.find("分享至")
        m = VIEW_RE_FALLBACK.search(html, start if start != -1 else 0)
    return int(m.group(1).replace(",", "")) if m else None


def check(client: httpx.Client, url: str, issue: str = "") -> dict:
    error = ""
    for attempt in range(RETRIES + 1):
        try:
            r = client.get(url)
            ok = r.status_code == 200
            return {
                "期別": issue,
                "url": url,
                "連線": "成功" if ok else "失敗",
                "狀態碼": r.status_code,
                "瀏覽次數": extract_views(r.text) if ok else None,
                "錯誤": "",
            }
        except httpx.HTTPError as e:
            error = f"{type(e).__name__}: {e}"
            if attempt < RETRIES:          # 最後一次失敗就不用再等
                time.sleep(2 * (attempt + 1))
    return {"期別": issue, "url": url, "連線": "失敗", "狀態碼": None, "瀏覽次數": None, "錯誤": error}


def ensure_history_header(history_path: str) -> None:
    """確保既有 view_history.csv 升級至最新表頭（補齊右側新欄位）。"""
    if not os.path.exists(history_path):
        with open(history_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(HISTORY_HEADER)
        return

    with open(history_path, "r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if not rows:
        with open(history_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerow(HISTORY_HEADER)
        return

    if rows[0] != HISTORY_HEADER:
        upgraded = [HISTORY_HEADER]
        for row in rows[1:]:
            if len(row) < len(HISTORY_HEADER):
                row = row + [""] * (len(HISTORY_HEADER) - len(row))
            upgraded.append(row)
        with open(history_path, "w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(upgraded)


def check_issue(issue_name: str, urls: list[str]) -> list[dict]:
    issue_results: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for idx, url in enumerate(urls):
            res = check(client, url, issue=issue_name)
            issue_results.append(res)
            views_str = res["瀏覽次數"] if res["瀏覽次數"] is not None else "-"
            print(f"[{issue_name}] {res['連線']}  {views_str:>8}  {url}  {res['錯誤']}", flush=True)
            if idx < len(urls) - 1:
                time.sleep(DELAY)
    return issue_results


def main(issues: dict[str, list[str]] = ISSUES) -> bool:
    results: list[dict] = []
    max_workers = max(1, min(2, len(issues)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            issue_name: pool.submit(check_issue, issue_name, urls)
            for issue_name, urls in issues.items()
        }
        for issue_name in issues:
            results.extend(futures[issue_name].result())

    now = datetime.now(ZoneInfo("Asia/Taipei"))   # GitHub 雲端主機是 UTC，統一用台灣時間
    out = f"views_{now:%Y%m%d_%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    ok = sum(r["連線"] == "成功" for r in results)
    issue_stats: dict[str, tuple[int, int, int | None]] = {}
    for issue_name in issues:
        sub = [r for r in results if r["期別"] == issue_name]
        sub_ok = sum(r["連線"] == "成功" for r in sub)
        sub_views = [r["瀏覽次數"] for r in sub if r["瀏覽次數"] is not None]
        issue_stats[issue_name] = (sub_ok, len(sub), max(sub_views) if sub_views else None)

    print(f"\n連線成功 {ok}/{len(results)}")
    for issue_name, (sub_ok, sub_total, max_v) in issue_stats.items():
        if max_v is not None:
            print(f"{issue_name} 瀏覽次數：{max_v}（連線 {sub_ok}/{sub_total}，本次檢查貢獻 {sub_ok} 次）")
    print(f"結果已存到 {out}")

    # 累積歷史：每次檢查追加一列到 view_history.csv（GitHub 上會被寫回 repo，直接看得到）
    history = "view_history.csv"
    ensure_history_header(history)
    failed = [
        f"{r['期別']}:{r['url'].rsplit('/', 1)[-1]}"
        for r in results
        if r["連線"] != "成功"
    ]
    vol54_max = issue_stats.get("Vol.54", (0, 0, None))[2]
    vol53_max = issue_stats.get("Vol.53", (0, 0, None))[2]
    with open(history, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            f"{now:%Y-%m-%d %H:%M:%S}",
            os.environ.get("GITHUB_EVENT_NAME", "local"),
            ok,
            len(results),
            vol54_max if vol54_max is not None else "",
            " ".join(failed),
            vol53_max if vol53_max is not None else "",
        ])
    print(f"歷史已追加到 {history}")

    # 在 GitHub Actions 上執行時，把結果表格顯示在執行頁面上（手機也看得到）
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## 型農本色連結檢查（{now:%Y-%m-%d %H:%M} 台灣時間）\n\n")
            parts = [f"**連線成功 {ok}/{len(results)}**"]
            for issue_name, (sub_ok, _, max_v) in issue_stats.items():
                if max_v is not None:
                    parts.append(f"**{issue_name} 瀏覽次數：{max_v}**（+{sub_ok}）")
            f.write("　｜　".join(parts))
            f.write("\n\n| 期別 | 網址 | 連線 | 狀態碼 | 瀏覽次數 | 錯誤 |\n|---|---|---|---|---|---|\n")
            for r in results:
                v_str = r["瀏覽次數"] if r["瀏覽次數"] is not None else "-"
                f.write(
                    f"| {r['期別']} | {r['url']} | {r['連線']} | {r['狀態碼'] or '-'} | "
                    f"{v_str} | {r['錯誤'] or ''} |\n"
                )

    return ok == len(results)


if __name__ == "__main__":
    # 有任何網址失敗就以錯誤碼結束，GitHub 會把這次執行標成失敗並寄信通知
    sys.exit(0 if main() else 1)
