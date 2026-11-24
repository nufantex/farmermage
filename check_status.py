"""逐一造訪型農本色電子期刊網址，回報「連線是否成功」與「瀏覽次數」。

用法：
    pip install httpx
    python check_status.py

注意：
- 網站會限制同時連線數，所以這裡刻意「一次一個、間隔 1 秒」。
- 瀏覽次數是「整期共用」的單一計數器，不是每篇各自計算；
  每造訪任何一頁都 +1，所以 12 頁會看到連續遞增的數字。
"""
from __future__ import annotations

import csv
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

URLS = [
    "https://www.kaofarmers.tw/farmer-colours/epaper/current-issue",
    *[f"https://www.kaofarmers.tw/farmer-colours/epaper/66/{n}" for n in range(561, 572)],
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
    )
}
TIMEOUT = 15
DELAY = 1.0
RETRIES = 2

# 實測原始 HTML：<span class="py-3 text-secondary"><i class="fas fa-eye"></i>14603次</span>
VIEW_RE = re.compile(r'fa-eye"\s*>\s*</i>\s*([\d,]+)\s*次')
VIEW_RE_FALLBACK = re.compile(r">\s*([\d,]+)\s*次\s*<")


def extract_views(html: str) -> int | None:
    m = VIEW_RE.search(html)
    if not m:  # 網站改版、眼睛圖示不見時的備援：從分享區塊之後找第一個「數字+次」
        start = html.find("分享至")
        m = VIEW_RE_FALLBACK.search(html, start if start != -1 else 0)
    return int(m.group(1).replace(",", "")) if m else None


def check(client: httpx.Client, url: str) -> dict:
    error = ""
    for attempt in range(RETRIES + 1):
        try:
            r = client.get(url)
            ok = r.status_code == 200
            return {
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
    return {"url": url, "連線": "失敗", "狀態碼": None, "瀏覽次數": None, "錯誤": error}


def main(urls: list[str] = URLS) -> bool:
    results = []
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for url in urls:
            res = check(client, url)
            results.append(res)
            views = res["瀏覽次數"] if res["瀏覽次數"] is not None else "-"
            print(f"{res['連線']}  {views:>8}  {url}  {res['錯誤']}")
            time.sleep(DELAY)

    now = datetime.now(ZoneInfo("Asia/Taipei"))   # GitHub 雲端主機是 UTC，統一用台灣時間
    out = f"views_{now:%Y%m%d_%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    ok = sum(r["連線"] == "成功" for r in results)
    views = [r["瀏覽次數"] for r in results if r["瀏覽次數"] is not None]
    print(f"\n連線成功 {ok}/{len(results)}")
    if views:
        # 整期（epaper/66）共用同一個計數器，每造訪一頁都 +1
        print(f"本期瀏覽次數：{max(views)}（本次檢查自己貢獻了 {ok} 次）")
    print(f"結果已存到 {out}")

    # 累積歷史：每次檢查追加一列到 view_history.csv（GitHub 上會被寫回 repo，直接看得到）
    history = "view_history.csv"
    new_file = not os.path.exists(history)
    failed = [r["url"].rsplit("/", 1)[-1] for r in results if r["連線"] != "成功"]
    with open(history, "a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["台灣時間", "觸發方式", "連線成功", "網址總數", "本期瀏覽次數", "失敗網址"])
        w.writerow([
            f"{now:%Y-%m-%d %H:%M:%S}",
            os.environ.get("GITHUB_EVENT_NAME", "local"),
            ok,
            len(results),
            max(views) if views else "",
            " ".join(failed),
        ])
    print(f"歷史已追加到 {history}")

    # 在 GitHub Actions 上執行時，把結果表格顯示在執行頁面上（手機也看得到）
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## 型農本色連結檢查（{now:%Y-%m-%d %H:%M} 台灣時間）\n\n")
            f.write(f"**連線成功 {ok}/{len(results)}**")
            if views:
                f.write(f"　｜　**本期瀏覽次數：{max(views)}**（含本次檢查的 {ok} 次）")
            f.write("\n\n| 網址 | 連線 | 狀態碼 | 瀏覽次數 | 錯誤 |\n|---|---|---|---|---|\n")
            for r in results:
                f.write(f"| {r['url']} | {r['連線']} | {r['狀態碼'] or '-'} | "
                        f"{r['瀏覽次數'] or '-'} | {r['錯誤'] or ''} |\n")

    return ok == len(results)


if __name__ == "__main__":
    # 有任何網址失敗就以錯誤碼結束，GitHub 會把這次執行標成失敗並寄信通知
    sys.exit(0 if main() else 1)
