import csv
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_status

COUNTERS = {"66": 14603, "65": 46533}
LOCK = threading.Lock()

PAGE = (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8" /></head><body>'
    '<div class="btn-group social_share" role="group">'
    '<span class="py-3 me-2 text-secondary"><i class="fas fa-share-alt"></i>\u5206\u4eab\u81f3</span>'
    "</div>"
    '<span class="py-3 text-secondary"><i class="fas fa-eye"></i>{views}\u6b21</span>'
    "<h3>Title</h3><article><p>Body text 3\u6b21 400\u6b21.</p></article>"
    "</body></html>"
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/missing"):
            self.send_response(404)
            self.end_headers()
            return
        issue_key = "65" if "/epaper/65" in self.path else "66"
        with LOCK:
            COUNTERS[issue_key] += 1
            n = COUNTERS[issue_key]
        body = PAGE.replace("{views}", str(n)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    real = '<span class="py-3 text-secondary"><i class="fas fa-eye"></i>14603\u6b21</span>'
    assert check_status.extract_views(real) == 14603
    assert check_status.extract_views("<p>No counter 3\u6b21</p>") is None
    assert check_status.extract_views('<i class="fas fa-eye"></i>1,234\u6b21') == 1234
    assert len(check_status.ISSUES["Vol.54"]) == 13
    assert len(check_status.ISSUES["Vol.53"]) == 13
    assert len(check_status.URLS) == 26
    print("Unit tests passed")

    check_status.DELAY = 0.02
    test_issues = {
        "Vol.54": [
            f"{base}/farmer-colours/epaper/current-issue",
            *[f"{base}/farmer-colours/epaper/66/{n}" for n in range(560, 572)],
            f"{base}/farmer-colours/epaper/missing",
        ],
        "Vol.53": [
            f"{base}/farmer-colours/epaper/65",
            *[f"{base}/farmer-colours/epaper/65/{n}" for n in range(548, 560)],
            "http://127.0.0.1:1/closed-port",
        ],
    }
    os.chdir(os.path.dirname(__file__))
    if os.path.exists("view_history.csv"):
        os.remove("view_history.csv")

    ok = check_status.main(test_issues)
    assert ok is False

    with open("view_history.csv", "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    assert rows[0] == check_status.HISTORY_HEADER
    last = rows[-1]
    assert last[2] == "26" and last[3] == "28"
    assert last[4] == "14616", f"Expected Vol.54=14616, got {last[4]}"
    assert last[6] == "46546", f"Expected Vol.53=46546, got {last[6]}"
    print("Integration tests passed")
    srv.shutdown()


if __name__ == "__main__":
    main()
