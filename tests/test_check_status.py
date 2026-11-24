"""用本機模擬伺服器測試 check_status.py。

模擬伺服器回傳的 HTML 依照 kaofarmers.tw 真實原始碼的結構（2026-11-20 抓取），
並模擬「整期共用一個瀏覽計數器、每次 GET +1」的行為。
"""
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["NO_PROXY"] = "127.0.0.1,localhost"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import check_status  # noqa: E402

COUNTER = {"n": 14603}
LOCK = threading.Lock()

PAGE = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8" />
<title>當期期刊-型農本色-型農大聯盟</title></head><body>
<div class="btn-group social_share" role="group">
  <span class="py-3 me-2 text-secondary"><i class="fas fa-share-alt"></i>分享至</span>
  <a class="btn btn-line" href="#">LINE</a>
</div>
<span class="py-3 text-secondary">
  <i class="fas fa-eye"></i>{views}次
</span>
<h3>文章標題</h3>
<article><p>王祈發說，最難忘的一次經驗是第3次移蜂，共搬了400次蜂箱。</p></article>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.endswith("/missing"):
            self.send_response(404)
            self.end_headers()
            return
        with LOCK:
            COUNTER["n"] += 1
            n = COUNTER["n"]
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

    # --- 單元測試：用真實擷取到的片段 ---
    real = '<span class="py-3 text-secondary"><i class="fas fa-eye"></i>14603次</span>'
    assert check_status.extract_views(real) == 14603
    assert check_status.extract_views("<p>沒有計數器，只有第3次</p>") is None
    assert check_status.extract_views('<i class="fas fa-eye"></i>1,234次') == 1234
    print("extract_views 單元測試：通過")

    # --- 整合測試：12 個正常網址 + 404 + 連不上的網址 ---
    check_status.DELAY = 0.05
    urls = [f"{base}/farmer-colours/epaper/current-issue"]
    urls += [f"{base}/farmer-colours/epaper/66/{n}" for n in range(561, 572)]
    urls += [f"{base}/farmer-colours/epaper/missing", "http://127.0.0.1:1/closed-port"]
    os.chdir(os.path.dirname(__file__))
    check_status.main(urls)
    srv.shutdown()


if __name__ == "__main__":
    main()
