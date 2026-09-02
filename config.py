"""全域設定。要改股票清單請編輯 tickers.txt，不用動這裡。"""

# ---- GitHub（請填入你的帳號，影響網頁上「編輯追蹤清單」的連結）----
GITHUB_USER = "rku413"
GITHUB_REPO = "pe-tracker-web"
GITHUB_BRANCH = "main"

# ---- 檔案路徑（相對於 repo 根目錄）----
TICKERS_FILE = "tickers.txt"
HISTORY_CSV = "data/history.csv"
OUTPUT_HTML = "index.html"

# ---- PE 分析參數 ----
PE_WINDOW_DAYS = 90          # 取最近 N 個交易日的收盤價算 PE 序列
SIGMA_THRESHOLD = 1.0        # 偏離幾個標準差算「顯著」
PRICE_HISTORY_PERIOD = "1y"  # 向 yfinance 要多長的歷史，再截取最後 PE_WINDOW_DAYS 天

# ---- 隱含波動率（IV）參數 ----
IV_TARGET_DAYS = 30          # 理想到期天數
IV_MIN_DAYS = 15             # 實際到期天數低於此值 → 標註
IV_MAX_DAYS = 45             # 實際到期天數高於此值 → 標註
IV_TIMEOUT_SEC = 45          # 單一股票抓選擇權鏈的逾時秒數，超過就跳過 IV 欄位
IV_REQUEST_DELAY_SEC = 4.0   # 每檔股票抓完選擇權後的延遲，避免 rate limit

# ---- IV Rank（IVR）參數：用 history.csv 每天累積的 IV 計算 ----
IVR_LOOKBACK_DAYS = 252      # 以最近 N 個交易日的 IV 高低區間計算（約一年）
IVR_MIN_DAYS = 20            # 累積不足 N 天時不顯示 IVR，只顯示累積進度
IV_SEEDS_FILE = "iv_seeds.json"  # 手動填的 52 週 IV 高低點種子，有種子的股票不必等累積
IV_SEED_MAX_AGE_DAYS = 365   # 種子日期超過此天數就失效（對應約 252 個交易日）

# ---- 一般抓取參數 ----
REQUEST_DELAY_SEC = 1.5      # 每檔股票基本資料抓完後的延遲

# ---- 顯示 ----
TIMEZONE = "Asia/Taipei"
