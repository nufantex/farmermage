# kaofarmer-monitor

每天自動檢查「型農本色」電子期刊（https://www.kaofarmers.tw/farmer-colours/epaper/）12 個網址：

- 連線是否成功（HTTP 200）
- 頁面顯示的瀏覽次數

## 怎麼看結果

到 GitHub 專案的 **Actions** 頁面 → 點最新一次執行，就能看到結果表格。
完整 CSV 在同一頁下方的 **Artifacts**，保留 90 天。
有任何網址失敗時，那次執行會標成紅色 ✗，GitHub 會寄信通知。

## 排程

- 每天台灣時間 08:17、11:17、14:17、17:17、20:17、23:17 自動執行（共 6 次）（`.github/workflows/check.yml`）
- 也可以在 Actions 頁面選「每日檢查型農本色連結」→「Run workflow」手動執行

## 注意事項

- **瀏覽次數是整期共用的一個計數器**，不是每篇各自計算；每造訪任何一頁都 +1。
  所以一次完整檢查會讓官方瀏覽數 +12，請不要把排程調得太頻繁。
- 網站會限制同時連線數，腳本刻意「一次一個、間隔 1 秒」逐一檢查。

## 本機執行

```bash
pip install httpx
python check_status.py          # 檢查真實網站
python tests/test_check_status.py  # 用本機模擬伺服器測試（不會連到真實網站）
```

需要 Python 3.9 以上。
