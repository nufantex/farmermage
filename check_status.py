from __future__ import annotations

import csv
import os
import re
import sys
import time
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

HISTORY_HEADER = ["timestamp", "event", "ok", "total", "vol54_views", "failed", "vol53_views"]

VIEW_RE = re.compile(r'fa-eye"\s*>\s*</i>\s*([\d,]+)\s*\u6b21')
VIEW_RE_FALLBACK = re.compile(r">\s*([\d,]+)\s*\u6b21\s*<")
SHARE_MARKER = "\u5206\u4eab\u81f3"


def extract_views(html: str) -> int | None:
    m = VIEW_RE.search(html)
    if not m:
        start = html.find(SHARE_MARKER)
        m = VIEW_RE_FALLBACK.search(html, start if start != -1 else 0)
    return int(m.group(1).replace(",", "")) if m else None


def check(client: httpx.Client, url: str, issue: str = "") -> dict:
    error = ""
    for attempt in range(RETRIES + 1):
        try:
            r = client.get(url)
            ok = r.status_code == 200
            return {
                "issue": issue,
                "url": url,
                "status": "OK" if ok else "FAIL",
                "code": r.status_code,
                "views": extract_views(r.text) if ok else None,
                "error": "",
            }
        except httpx.HTTPError as e:
            error = f"{type(e).__name__}: {e}"
            if attempt < RETRIES:
                time.sleep(2 * (attempt + 1))
    return {"issue": issue, "url": url, "status": "FAIL", "code": None, "views": None, "error": error}


def ensure_history_header(history_path: str) -> None:
    if not os.path.exists(history_path):
        with open(history_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HISTORY_HEADER)
        return

    with open(history_path, "r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    if not rows:
        with open(history_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(HISTORY_HEADER)
        return

    if rows[0] != HISTORY_HEADER:
        upgraded = [HISTORY_HEADER]
        for row in rows[1:]:
            if len(row) < len(HISTORY_HEADER):
                row = row + [""] * (len(HISTORY_HEADER) - len(row))
            upgraded.append(row)
        with open(history_path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(upgraded)


def main(issues: dict[str, list[str]] = ISSUES) -> bool:
    results: list[dict] = []
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        for issue_name, urls in issues.items():
            for url in urls:
                res = check(client, url, issue=issue_name)
                results.append(res)
                views_str = res["views"] if res["views"] is not None else "-"
                print(f"[{issue_name}] {res['status']:<4}  {views_str:>8}  {url}  {res['error']}")
                time.sleep(DELAY)

    now = datetime.now(ZoneInfo("Asia/Taipei"))
    out = f"views_{now:%Y%m%d_%H%M%S}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    ok = sum(r["status"] == "OK" for r in results)
    issue_stats: dict[str, tuple[int, int, int | None]] = {}
    for issue_name in issues:
        sub = [r for r in results if r["issue"] == issue_name]
        sub_ok = sum(r["status"] == "OK" for r in sub)
        sub_views = [r["views"] for r in sub if r["views"] is not None]
        issue_stats[issue_name] = (sub_ok, len(sub), max(sub_views) if sub_views else None)

    print(f"\nOK {ok}/{len(results)}")
    for issue_name, (sub_ok, sub_total, max_v) in issue_stats.items():
        if max_v is not None:
            print(f"{issue_name} views: {max_v} ({sub_ok}/{sub_total}, +{sub_ok})")
    print(f"Saved: {out}")

    history = "view_history.csv"
    ensure_history_header(history)
    failed = [
        f"{r['issue']}:{r['url'].rsplit('/', 1)[-1]}"
        for r in results
        if r["status"] != "OK"
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
    print(f"Appended: {history}")

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"## Check ({now:%Y-%m-%d %H:%M})\n\n")
            parts = [f"**OK {ok}/{len(results)}**"]
            for issue_name, (sub_ok, _, max_v) in issue_stats.items():
                if max_v is not None:
                    parts.append(f"**{issue_name}: {max_v}** (+{sub_ok})")
            f.write(" | ".join(parts))
            f.write("\n\n| Issue | URL | Status | Code | Views | Error |\n|---|---|---|---|---|---|\n")
            for r in results:
                v_str = r["views"] if r["views"] is not None else "-"
                f.write(
                    f"| {r['issue']} | {r['url']} | {r['status']} | {r['code'] or '-'} | "
                    f"{v_str} | {r['error'] or ''} |\n"
                )

    return ok == len(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
