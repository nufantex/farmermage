# farmermage

每天自動檢查「型農本色」電子期刊（https://www.kaofarmers.tw/farmer-colours/epaper/）12 個網址，共執行 **50 次**：

- 連線是否成功（HTTP 200）
- 頁面顯示的瀏覽次數
- 自動累積紀錄到 [view_history.csv](view_history.csv)

## 怎麼看結果

1. **累積趨勢**：直接查看 repo 內的 [view_history.csv](view_history.csv)，每次執行都會自動追加一列（台灣時間、觸發方式、連線成功數、本期瀏覽次數、失敗網址）。
2. **單次明細**：到 GitHub 專案的 **Actions** 頁面 → 點最新一次執行，即可在 Summary 看到 12 個網址的結果表格；完整 CSV 在同一頁下方的 **Artifacts**，保留 90 天。
3. **異常通知**：有任何網址失敗時，該次執行會標成紅色 ✗，GitHub 會寄信通知（同時仍會寫入 `view_history.csv` 與上傳 CSV）。

## 排程架構（每天 50 次）

為避免 GitHub Actions 內建 `schedule` 延遲與漏跑，排程改由 **Cloudflare Workers Cron Triggers**（`farmermage-cron`，原始碼見 [`worker/index.js`](worker/index.js)）穩定觸發 GitHub Actions（[`.github/workflows/check.yml`](.github/workflows/check.yml)）的 `workflow_dispatch`：

- `7,22,37,52 * * * *` 與 `14,44 4,16 * * *`（共用 2 條 Cron，依分鐘數分流）：
  - **`nufantex/farmermage`**：每小時 `:07`、`:37` ＋台灣時間 `00:14`、`12:14`（**每天 50 次**）
  - **`chingfonlee/Katharine-s-monitor`**：每小時 `:22`、`:52` ＋台灣時間 `00:44`、`12:44`（**每天 50 次**）
- 兩邊全程錯開 7～15 分鐘，避免同時連線到網站
- 也可以在 Actions 頁面選「每日 50 次檢查型農本色連結」→「Run workflow」手動執行

### Cloudflare Worker 設定說明

- Worker 名稱：`farmermage-cron`
- 純文字變數（Vars）：`GITHUB_OWNER`、`GITHUB_REPO`、`GITHUB_WORKFLOW`、`GITHUB_REF`（以及對應的 `*_CHINGFONLEE`）
- 機密變數（Secrets）：
  - `GITHUB_TOKEN`（`nufantex/farmermage` 的 **Actions: Read and write**）
  - `GITHUB_TOKEN_CHINGFONLEE`（`chingfonlee/Katharine-s-monitor` 的 **Actions: Read and write**）

## 注意事項

- **瀏覽次數是整期共用的一個計數器**，不是每篇各自計算；每造訪任何一頁都 +1。
  - 每次完整檢查 12 個網址會讓官方瀏覽數 +12。
  - 每天執行 50 次合計會為官方瀏覽數帶來約 +600 次瀏覽。
- 網站會限制同時連線數，腳本刻意「一次一個、間隔 1 秒」逐一檢查，並在網路錯誤時最多重試 2 次。

## 本機執行

```bash
pip install httpx
python check_status.py             # 檢查真實網站（12 個網址）
python tests/test_check_status.py  # 用本機模擬伺服器測試（不會連到真實網站）
```

需要 Python 3.9 以上（Windows 環境若缺少系統時區資料，請一併安裝 `pip install tzdata`）。
