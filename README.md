# PE Tracker Web

每天台灣時間 05:30 由 GitHub Actions 自動抓取 Yahoo Finance 資料、計算估值指標，
並產生靜態網頁 `index.html`，透過 GitHub Pages 公開。

## 修改追蹤清單

1. 在 GitHub 上打開 `tickers.txt`
2. 點右上角鉛筆圖示（Edit）
3. 一行一個股票代碼，`#` 開頭為註解。台股加 `.TW`（例如 `2330.TW`）
4. 按 Commit changes

下一次排程或手動觸發時就會套用新清單。

## IV Rank 怎麼來的

yfinance 沒有歷史 IV，所以程式每天把 ATM call 的 IV 存進 `data/history.csv`，
再用自己累積的最近 252 個交易日算 IV Rank。累積不足 20 天時顯示「資料累積中」，
不足 252 天時會標註實際天數。**不要刪 history.csv**，刪了 IVR 就要重新累積。

不想等累積的話，把該股票的 52 週 IV 最高 / 最低值與發生日期填進 `iv_seeds.json`
（Barchart 的 Options Overview History 頁面有），程式會把種子和累積資料一起取極值，
當天就能顯示 IVR，並標「種子」。種子日期超過 365 天自動失效。新增股票時記得順手加一筆。

## 手動更新一次

Actions 分頁 → 左側選 **Daily PE update** → 右側 **Run workflow** → Run。

## 本機測試

```bash
pip install -r requirements.txt
python main.py           # 完整執行（含選擇權 IV，較慢）
python main.py --no-iv   # 跳過 IV，快速測試
```

## 檔案

| 檔案 | 用途 |
| --- | --- |
| `tickers.txt` | 追蹤清單（唯一需要手動維護的檔案） |
| `config.py` | 參數：GitHub 帳號、90 天視窗、σ 門檻、IV 到期天數與逾時 |
| `fetch_data.py` | yfinance 抓取（股價、info 欄位、選擇權鏈） |
| `metrics.py` | 純計算：PE 統計、估值價、分組、PCF、PEG、殖利率、52 週位置 |
| `render_html.py` | 產生 `index.html` |
| `main.py` | 入口，串起以上並追加 `data/history.csv` |
| `.github/workflows/daily-update.yml` | 排程與手動觸發 |
