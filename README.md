# 台股大盤 + 自選個股 Market Regime Dashboard

以繁體中文實作的台股市場狀態與自選個股觀察系統（Market Observation System）。

## 核心設計原則
`State + Change + Trend + Acceleration + Relative Strength + Historical Percentile → Regime`
- **不堆砌大量重複技術指標**（動能僅採用 RSI、MACD、ROC）
- **不做價格預測、不把分數當成買賣訊號**：所有 0–100 分數皆為「資訊壓縮後的狀態」
- **對缺失資料誠實**：缺失值顯示 `N/A（Data unavailable）`，絕不補 `0`，權重自動正規化重分配

## 專案目錄結構
```text
TW stock dashboard 2/
├── backend/
│   ├── config/
│   │   ├── settings.yaml       # 所有權重 / 門檻 / 時間窗 / 資料源集中設定（不散落於前端）
│   │   ├── watchlist.csv       # 自選股名單（可隨時用 Excel / 文字編輯器增刪，亦可在 UI 新增刪除）
│   │   └── universe.csv        # 市場廣度與類股輪動樣本股清單
│   ├── app/
│   │   ├── config.py           # 設定與 CSV 讀寫
│   │   ├── ingest.py           # 資料擷取與快取層（FinMind / TWSE / TPEx / Yahoo）
│   │   ├── indicators.py       # 指標計算純函式（SMA / EMA / RSI / MACD / ROC / ATR / OBV / 波動度）
│   │   ├── timeseries.py       # 時間維度純函式（Change / Normalized Slope / Acceleration / Percentile / Z-score）
│   │   ├── scoring.py          # Market Score & Stock Score 引擎
│   │   ├── regime.py           # 10 種 Market / Stock Regime 分類器
│   │   ├── alerts.py           # 背離偵測（Divergence）与 Regime Change 警示引擎
│   │   ├── service.py          # Snapshot 編排層
│   │   └── main.py             # FastAPI REST 端點
│   └── tests/
│       └── test_core.py        # 31 項確定性單元測試
└── frontend/
    └── src/
        ├── format.ts           # 全站固定語意色（綠=正向 / 紅=負向 / 黃=警示 / 灰=中性）与數值格式化
        ├── api.ts              # REST API hook
        └── components/
            ├── MarketDashboard.tsx  # 首頁九大區塊 + 30 秒十問快答 + 第二層展開
            ├── WatchlistView.tsx    # 自選股看板（與 watchlist.csv 雙向同步）
            ├── StockDetail.tsx      # 個股深度頁（K線+均線、RS、RSI/MACD/ROC、OBV/ATR、法人、融資券、基本面）
            ├── AlertsView.tsx       # 警示中心（Market / Sector / Stock）
            ├── TimeDimension.tsx    # Current | 1D | 5D | 20D | 60D | Slope/Accel | Percentile | Sparkline
            └── Charts.tsx           # TradingView Lightweight Charts 封裝與類股 Treemap
```

## 自選股 CSV 格式（`backend/config/watchlist.csv`）
```csv
symbol,name,market,sector
2330,台積電,TWSE,半導體
2454,聯發科,TWSE,半導體
2317,鴻海,TWSE,AI伺服器/電子代工
```
- `market`：`TWSE`（上市）或 `TPEx`（上櫃）
- 直接編輯存檔後，於網頁右上角點選「↻ 重新抓取」即可生效；或直接在「自選股 Watchlist (CSV)」分頁新增／移除。

## 啟動方式
```bash
# 1. 後端 API（Port 8000）
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# 2. 前端開發伺服器（Port 5173，已設定 /api 代理至 8000）
cd frontend
npm run dev

# 3. 執行單元測試
cd backend
.venv/bin/pytest
```
