# 台股大盤 + 自選個股 Market Regime Dashboard

> **Don’t show more data. Show more context.**
>
> `Current state` 告訴我們現在在哪裡 · `Change` 告訴我們發生了什麼 · `Trend` 告訴我們往哪裡走 · `Acceleration` 告訴我們變化在加速或減速 · `Relative Strength` 告訴我們誰在領先 · `Historical Percentile` 告訴我們目前有多極端 · `Regime` 告訴我們這代表什麼意義。

- **線上瀏覽（GitHub Pages）**：<https://mimiba0925.github.io/tw_stock_regime_dashboard/>
- **GitHub 儲存庫**：<https://github.com/mimiba0925/tw_stock_regime_dashboard>

---

## 一、產品定位與核心目標

本系統是 **台股市場狀態觀察系統（Market Observation System）**，而非傳統技術分析指標堆砌工具或買賣訊號產生器。

打開首頁 **30 秒內**，即可直接回答以下 10 個核心問題：
1. **現在台股是多頭 / 空頭 / 中性？**（Market Regime 10 態分類 + 0–100 總分）
2. **這個趨勢正在變強還是變弱？變化是在加速還是減速？**（Normalized Slope + Acceleration）
3. **市場廣度是否支持指數？**（站上 MA20 / MA60 / MA120 比例、漲跌家數比、52W 新高新低）
4. **外資 / 投信正在買還是賣？買賣力道在擴大還是縮小？**（1D / 5D / 20D / 60D 累計與 Flow State）
5. **成交量是在支持還是背離價格？**（價量四象限視覺化 + 20D / 60D / 250D 歷史百分位）
6. **哪些類股正在領導？哪些類股正在轉弱？**（15 大類股 Treemap + 相對大盤 RS 與輪動方向）
7. **我的自選股誰最強？是否強於大盤與所屬類股？**（RS Score 0–100 橫斷面百分位）
8. **個股目前處於什麼 Regime？六大面向（趨勢/動能/量能/籌碼/RS/基本面）強弱如何？**
9. **哪些指標出現背離（Divergence）或發生狀態改變（Regime Change）？**
10. **目前是正常回檔，還是可能的市場結構改變？**

---

## 二、系統架構與目錄結構

```text
TW stock dashboard 2/
├── .github/workflows/
│   └── update_data.yml          # GitHub Actions 雲端全自動定時更新與部署工作流
├── backend/                     # Python FastAPI 計算引擎與 API 層
│   ├── config/
│   │   ├── settings.yaml        # 集中設定檔（分數權重 / 門檻 / Regime 規則 / 時間窗 / 資料源）
│   │   ├── watchlist.csv        # 自選股清單 CSV（自動依股票代碼排序，支援雙向同步）
│   │   └── universe.csv         # 市場廣度與 15 大類股輪動樣本股池（64 檔代表股）
│   ├── app/
│   │   ├── config.py            # 設定載入、台北時區 (Asia/Taipei) 與 CSV 自動排序讀寫
│   │   ├── ingest.py            # 資料擷取與快取層（FinMind / TWSE / TPEx / Yahoo Finance）
│   │   ├── indicators.py        # 指標計算純函式（SMA / EMA / RSI / MACD / ROC / ATR / OBV / 波動度）
│   │   ├── timeseries.py        # 時間維度純函式（Change / Normalized Slope / Acceleration / Percentile / Z-score）
│   │   ├── scoring.py           # Market Score & Stock Score 0–100 正規化評分引擎
│   │   ├── regime.py            # 10 種 Market / Stock Regime 綜合分類器
│   │   ├── alerts.py            # 背離偵測（Divergence）與 Regime Change 警示引擎
│   │   ├── service.py           # Snapshot 編排與歷史狀態回溯比較
│   │   └── main.py              # FastAPI REST API（13 個資料端點）
│   ├── tests/
│   │   └── test_core.py         # 31 項確定性單元測試（pytest）
│   └── requirements.txt
├── frontend/                    # React 19 + TypeScript + Tailwind CSS + Lightweight Charts
│   └── src/
│       ├── App.tsx              # 頂部導覽、深淺色模式切換、雲端/本機更新入口
│       ├── api.ts               # 自動切換「GitHub Pages 靜態快照模式」與「本機 FastAPI 即時模式」
│       ├── format.ts            # 全站固定顏色語意與數值/金額/張數格式化
│       └── components/
│           ├── MarketDashboard.tsx  # 首頁（第一層 9 大區塊 + 30 秒 10 問快答 + 第二層展開）
│           ├── WatchlistView.tsx    # 自選股看板（預設及增刪後自動依股票代碼排序）
│           ├── StockDetail.tsx      # 個股深度頁（K線+均線、RS、RSI/MACD/ROC、OBV/ATR、法人、融資券、基本面）
│           ├── AlertsView.tsx       # 警示中心（Market / Sector / Stock 分類檢視）
│           ├── TimeDimension.tsx    # 時間維度橫列元件（Current | 1D | 5D | 20D | 60D | Slope/Accel | Percentile | Sparkline）
│           ├── Charts.tsx           # TradingView Lightweight Charts 封裝與類股 Treemap
│           └── ui.tsx               # Gauge、ScoreBar、Bars、Sparkline、QualityBadge
├── build_static.py              # 將後端完整計算結果匯出為根目錄 snapshot.js + 打包前端靜態檔
├── sync_github.py               # 本機一鍵更新資料並同步推送至 GitHub Pages
├── index.html                   # GitHub Pages 根目錄入口
├── snapshot.js                  # 預先計算之完整靜態資料快照
└── workthrough.md               # 完整設計與實作 Walkthrough 文件
```

---

## 三、自選股 CSV 管理（`backend/config/watchlist.csv`）

自選股名單獨立收列於 [`backend/config/watchlist.csv`](backend/config/watchlist.csv)，格式如下：

```csv
symbol,name,market,sector
1519,華城,TWSE,電機機械
2308,台達電,TWSE,電子零組件
2317,鴻海,TWSE,AI伺服器/電子代工
2330,台積電,TWSE,半導體
2382,廣達,TWSE,AI伺服器/電子代工
2454,聯發科,TWSE,半導體
2603,長榮,TWSE,航運
2881,富邦金,TWSE,金融
3231,緯創,TWSE,AI伺服器/電子代工
6669,緯穎,TWSE,AI伺服器/電子代工
```
- `market` 欄位填寫 `TWSE`（上市）或 `TPEx`（上櫃）。
- **自動依代碼排序**：無論在檔案最後一行新增哪一檔股票，系統讀取與寫回時都會自動依股票代碼數值由小到大排序；前端 Watchlist 表格亦預設以股票代碼排序。
- **三種編輯方式**：
  1. **GitHub 網頁直接改（免開電腦）**：點選介面上的「點此直接在 GitHub 線上編輯 `watchlist.csv`」，修改後按 `Commit changes`，GitHub Actions 會自動重算並更新網站。
  2. **本機編輯 CSV**：直接用 Excel 或文字編輯器修改 `backend/config/watchlist.csv`，執行 `python3 sync_github.py`。
  3. **本機網頁 UI 增刪**：在本機啟動前後端時，可於「自選股 Watchlist (CSV)」分頁直接輸入代號新增或點擊 `✕` 刪除，會即時寫回 `watchlist.csv`。

---

## 四、雲端全自動更新時程（GitHub Actions）

[`.github/workflows/update_data.yml`](.github/workflows/update_data.yml) 會在每個交易日（週一至週五）依台灣時間（`Asia/Taipei`）自動執行 **4 次** 更新：

| 台灣時間 (TST) | Cron (UTC) | 更新重點 |
| :--- | :--- | :--- |
| **14:25** | `25 6 * * 1-5` | 台股收盤行情、大盤成交額、個股 OHLCV、市場廣度、類股輪動、價格突破/跌破警示 |
| **17:20** | `20 9 * * 1-5` | 三大法人買賣超金額（大盤 BFI82U）與個股三大法人買賣超張數（T86）、籌碼分數 |
| **21:45** | `45 13 * * 1-5` | 個股融資融券餘額、本益比 PE / 股價淨值比 PB / 殖利率、最新月營收 YoY |
| **06:30** | `30 22 * * 1-5` | 美股收盤後更新外部風險背景（VIX、費半 SOX、Nasdaq、S&P 500、US10Y、USD/TWD） |

- **隨時手動更新**：點選網頁右上角「**⚡ 雲端自動更新 / 手動觸發**」→ 在 GitHub Actions 頁面點選 **Run workflow**，約 1 分鐘即更新完成。

---

## 五、本機開發與執行方式

### 1. 啟動後端 FastAPI（Port 8000）
```bash
cd backend
uv venv .venv
uv pip install -p .venv -r requirements.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### 2. 啟動前端 Vite 開發伺服器（Port 5173）
```bash
cd frontend
npm install
npm run dev
```
打開瀏覽器前往 `http://127.0.0.1:5173`。

### 3. 本機一鍵更新靜態快照並同步至 GitHub Pages
```bash
python3 sync_github.py
```

### 4. 執行確定性單元測試（31 項）
```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest -v backend/tests
```
