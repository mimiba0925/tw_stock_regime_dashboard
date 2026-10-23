"""Data ingestion layer：Yahoo Finance、TWSE、TPEx。

每份快取都記錄 source / data_timestamp / update_time，供前端顯示資料新鮮度。
儲存層為檔案快取（JSON），介面集中於 Cache 類別，未來可替換為 PostgreSQL / Redis。
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import requests

from .config import get_settings, now_taipei, resolve, today_taipei

log = logging.getLogger("ingest")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}
_YAHOO_LOCK = threading.Lock()
_LAST_YAHOO_REQ = 0.0


# ============================================================
# Cache
# ============================================================
class Cache:
    def __init__(self) -> None:
        self.root = resolve(get_settings()["data_source"]["cache_dir"])
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, kind: str, key: str) -> Path:
        d = self.root / kind
        d.mkdir(parents=True, exist_ok=True)
        safe = key.replace("/", "_").replace("^", "IDX_").replace("=", "_")
        return d / f"{safe}.json"

    def get(self, kind: str, key: str, ttl_sec: float | None = None) -> dict | None:
        p = self._path(kind, key)
        if not p.exists():
            return None
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
        if ttl_sec is not None:
            upd = datetime.fromisoformat(obj["meta"]["update_time"])
            if (now_taipei() - upd).total_seconds() > ttl_sec:
                return None
        return obj

    def put(self, kind: str, key: str, data: Any, source: str, data_timestamp: str | None) -> dict:
        obj = {
            "meta": {
                "source": source,
                "data_timestamp": data_timestamp,
                "update_time": now_taipei().isoformat(timespec="seconds"),
            },
            "data": data,
        }
        with self._lock:
            self._path(kind, key).write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        return obj


CACHE = Cache()


def _http_json(url: str, *, method: str = "GET", data: dict | None = None) -> Any:
    timeout = get_settings()["data_source"]["http_timeout_sec"]
    r = requests.request(method, url, headers=UA, data=data, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _num(x: Any) -> float | None:
    if x is None:
        return None
    s = str(x).replace(",", "").replace("+", "").strip()
    if s in ("", "--", "-", "N/A", "X"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ============================================================
# FinMind（台股個股與加權指數 OHLCV + 三大法人 + 融資融券）
# ============================================================
def fetch_tw_price(symbol: str, force: bool = False) -> pd.DataFrame | None:
    """台股代號（如 '2330'、'5347'）或 'TAIEX'。優先使用 FinMind，快速且不限頻。"""
    cfg = get_settings()
    ttl = cfg["update"]["price_refresh_minutes"] * 60
    cached = None if force else CACHE.get("tw_price", symbol, ttl)
    if cached is None:
        start = (today_taipei() - timedelta(days=760)).isoformat()
        token = os.environ.get("FINMIND_TOKEN", "").strip()
        extra = f"&token={token}" if token else ""
        try:
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={symbol}&start_date={start}{extra}"
            j = _http_json(url)
            data = j.get("data") or []
            rows = [
                [r["date"], r["open"], r["max"], r["min"], r["close"], r.get("Trading_Volume") or 0, r.get("Trading_money") or 0]
                for r in data if r.get("close")
            ]
            if rows:
                cached = CACHE.put("tw_price", symbol, {"rows": rows}, "FinMind / TWSE·TPEx", rows[-1][0])
        except Exception as e:  # noqa: BLE001
            log.warning("finmind price %s: %s", symbol, e)
            cached = CACHE.get("tw_price", symbol)
    if not cached or not cached["data"].get("rows"):
        return None
    df = pd.DataFrame(cached["data"]["rows"], columns=["date", "open", "high", "low", "close", "volume", "turnover"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date", keep="last").set_index("date").sort_index().astype(float)
    df.attrs["meta"] = cached["meta"]
    return df


# ============================================================
# Yahoo Finance（國際市場指數 / 匯率）
# ============================================================
def fetch_yahoo(symbol: str, rng: str | None = None, force: bool = False) -> pd.DataFrame | None:
    cfg = get_settings()
    rng = rng or cfg["data_source"]["price_history_range"]
    ttl = cfg["update"]["price_refresh_minutes"] * 60
    cached = None if force else CACHE.get("yahoo", symbol, ttl)
    if cached is None:
        try:
            global _LAST_YAHOO_REQ
            with _YAHOO_LOCK:
                wait = 0.25 - (time.time() - _LAST_YAHOO_REQ)
                if wait > 0:
                    time.sleep(wait)
                _LAST_YAHOO_REQ = time.time()
            url = f"https://query2.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?range={rng}&interval=1d"
            j = _http_json(url)
            res = j["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            ts = res.get("timestamp") or []
            tz_off = res["meta"].get("gmtoffset", 0)
            rows = []
            for i, t in enumerate(ts):
                d = datetime.utcfromtimestamp(t + tz_off).date().isoformat()
                c = q["close"][i]
                if c is None:
                    continue
                rows.append([d, q["open"][i], q["high"][i], q["low"][i], c, q["volume"][i]])
            name = res["meta"].get("shortName") or res["meta"].get("longName")
            cached = CACHE.put("yahoo", symbol, {"rows": rows, "name": name}, "Yahoo Finance",
                               rows[-1][0] if rows else None)
        except Exception as e:  # noqa: BLE001
            log.warning("yahoo %s failed: %s", symbol, e)
            cached = CACHE.get("yahoo", symbol)  # 退回舊快取（可能 stale）
            if cached is None:
                return None
    rows = cached["data"]["rows"]
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date", keep="last").set_index("date").sort_index()
    df = df.astype(float)
    df.attrs["meta"] = cached["meta"]
    return df


# ============================================================
# TWSE 大盤成交資訊（月資料：成交金額 / 股數 / 加權指數）
# ============================================================
def _months_back(n: int) -> list[date]:
    today = today_taipei().replace(day=1)
    out = []
    y, m = today.year, today.month
    for _ in range(n):
        out.append(date(y, m, 1))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def _roc_to_iso(s: str) -> str:
    s = s.strip().replace("/", "")
    if len(s) == 7:  # 1151022
        return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:7]}"
    y, m, d = s.split("-") if "-" in s else (s[:-4], s[-4:-2], s[-2:])
    return f"{int(y) + 1911}-{m}-{d}"


def _month_cached(kind: str, month: date, fetch: Callable[[], Any], source: str) -> Any:
    key = month.strftime("%Y%m")
    t = today_taipei()
    is_current = month.year == t.year and month.month == t.month
    ttl = get_settings()["update"]["price_refresh_minutes"] * 60 if is_current else None
    c = CACHE.get(kind, key, ttl)
    if c is not None:
        return c["data"]
    try:
        data = fetch()
        CACHE.put(kind, key, data, source, None)
        time.sleep(get_settings()["data_source"]["twse_request_interval_sec"])
        return data
    except Exception as e:  # noqa: BLE001
        log.warning("%s %s failed: %s", kind, key, e)
        c = CACHE.get(kind, key)
        return c["data"] if c else []


def fetch_twse_turnover() -> pd.DataFrame | None:
    n = get_settings()["data_source"]["index_history_months"]
    rows: list[list] = []
    for m in _months_back(n):
        def f(m=m):
            j = _http_json(f"https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?response=json&date={m:%Y%m%d}")
            if j.get("stat") != "OK":
                return []
            out = []
            for r in j.get("data", []):
                y, mo, d = r[0].split("/")
                out.append([f"{int(y) + 1911}-{mo}-{d}", _num(r[1]), _num(r[2]), _num(r[4])])
            return out
        rows += _month_cached("twse_fmtqik", m, f, "TWSE FMTQIK")
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "shares", "turnover", "taiex"])
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates("date").set_index("date").sort_index()


def fetch_tpex_index() -> pd.DataFrame | None:
    n = get_settings()["data_source"]["index_history_months"]
    rows: list[list] = []
    for m in _months_back(n):
        def f(m=m):
            j = _http_json("https://www.tpex.org.tw/www/zh-tw/indexInfo/inx", method="POST",
                           data={"date": m.strftime("%Y/%m/01"), "response": "json"})
            tables = j.get("tables") or []
            if not tables:
                return []
            return [[r[0].replace("/", "-"), _num(r[1]), _num(r[2]), _num(r[3]), _num(r[4])]
                    for r in tables[0].get("data", [])]
        rows += _month_cached("tpex_index", m, f, "TPEx 櫃買指數")
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df["volume"] = float("nan")
    return df.dropna(subset=["close"]).drop_duplicates("date").set_index("date").sort_index()


# ============================================================
# TWSE 三大法人（逐日）
# ============================================================
def _daily_cached(kind: str, d: date, fetch: Callable[[], Any], source: str) -> tuple[Any, bool]:
    """回傳 (data, fetched_from_network)。過去日期的結果永久快取。"""
    key = d.strftime("%Y%m%d")
    is_today = d >= date.today()
    c = CACHE.get(kind, key, 30 * 60 if is_today else None)
    if c is not None:
        return c["data"], False
    data = fetch()
    if data is None:  # 網路錯誤不快取
        return None, True
    if data or not is_today:
        CACHE.put(kind, key, data, source, d.isoformat())
    return data, True


def _fetch_bfi82u(d: date) -> dict | None:
    try:
        j = _http_json(f"https://www.twse.com.tw/rwd/zh/fund/BFI82U?response=json&dayDate={d:%Y%m%d}&type=day")
    except Exception as e:  # noqa: BLE001
        log.warning("BFI82U %s: %s", d, e)
        return None
    if j.get("stat") != "OK":
        return {}
    rows = {r[0]: _num(r[3]) for r in j.get("data", [])}
    dealer = (rows.get("自營商(自行買賣)") or 0) + (rows.get("自營商(避險)") or 0)
    foreign = (rows.get("外資及陸資(不含外資自營商)") or 0) + (rows.get("外資自營商") or 0)
    return {"foreign": foreign, "trust": rows.get("投信"), "dealer": dealer, "total": rows.get("合計")}


def _fetch_t86(d: date) -> dict | None:
    try:
        j = _http_json(f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={d:%Y%m%d}&selectType=ALLBUT0999")
    except Exception as e:  # noqa: BLE001
        log.warning("T86 %s: %s", d, e)
        return None
    if j.get("stat") != "OK":
        return {}
    f = j["fields"]
    idx = {k: f.index(k) for k in f}
    out = {}
    for r in j.get("data", []):
        code = r[0].strip()
        out[code] = [
            _num(r[idx["外陸資買賣超股數(不含外資自營商)"]]),
            _num(r[idx["投信買賣超股數"]]),
            _num(r[idx["自營商買賣超股數"]]),
        ]
    return out


class InstitutionalLoader:
    """背景逐日抓取法人資料（TWSE 有頻率限制，首次需數分鐘）。"""

    def __init__(self) -> None:
        self.progress = {"market": [0, 0], "stock": [0, 0], "running": False, "last_run": None}
        self._lock = threading.Lock()

    def run(self, trading_days: list[date]) -> None:
        if not self._lock.acquire(blocking=False):
            return
        try:
            cfg = get_settings()["data_source"]
            interval = cfg["twse_request_interval_sec"]
            self.progress["running"] = True
            mk_days = trading_days[-cfg["institutional_history_days"]:]
            st_days = set(trading_days[-cfg["stock_institutional_history_days"]:])
            self.progress["market"] = [0, len(mk_days)]
            self.progress["stock"] = [0, len(st_days)]
            for d in reversed(mk_days):  # 由近到遠，讓最新資料先可用
                _, net = _daily_cached("twse_bfi82u", d, lambda d=d: _fetch_bfi82u(d), "TWSE BFI82U")
                if net:
                    time.sleep(interval)
                self.progress["market"][0] += 1
                if d in st_days:
                    _, net = _daily_cached("twse_t86", d, lambda d=d: _fetch_t86(d), "TWSE T86")
                    if net:
                        time.sleep(interval)
                    self.progress["stock"][0] += 1
            self.progress["last_run"] = datetime.now().isoformat(timespec="seconds")
        finally:
            self.progress["running"] = False
            self._lock.release()


INST_LOADER = InstitutionalLoader()


def _fm_token() -> str:
    t = os.environ.get("FINMIND_TOKEN", "").strip()
    return f"&token={t}" if t else ""


def load_market_institutional(trading_days: list[date], force: bool = False) -> pd.DataFrame | None:
    """全市場三大法人買賣超金額（元）。一次抓取區間，秒級完成。"""
    ttl = get_settings()["update"]["price_refresh_minutes"] * 60
    c = None if force else CACHE.get("market_inst", "all", ttl)
    if c is None:
        start = (today_taipei() - timedelta(days=400)).isoformat()
        try:
            j = _http_json(f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockTotalInstitutionalInvestors&start_date={start}{_fm_token()}")
            by_date: dict[str, dict[str, float]] = {}
            for r in j.get("data") or []:
                d = by_date.setdefault(r["date"], {"foreign": 0.0, "trust": 0.0, "dealer": 0.0, "total": 0.0})
                net = float((r.get("buy") or 0) - (r.get("sell") or 0))
                nm = r.get("name")
                if nm in ("Foreign_Investor", "Foreign_Dealer_Self"):
                    d["foreign"] += net
                elif nm == "Investment_Trust":
                    d["trust"] += net
                elif nm in ("Dealer_self", "Dealer_Hedging"):
                    d["dealer"] += net
                elif nm == "total":
                    d["total"] = net
            rows = [{"date": k, **v} for k, v in sorted(by_date.items())]
            if rows:
                c = CACHE.put("market_inst", "all", rows, "FinMind / TWSE BFI82U", rows[-1]["date"])
        except Exception as e:  # noqa: BLE001
            log.warning("market_inst: %s", e)
            c = CACHE.get("market_inst", "all")
    if not c or not c["data"]:
        return None
    df = pd.DataFrame(c["data"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)


def load_stock_institutional(code: str, trading_days: list[date] | None = None, force: bool = False) -> pd.DataFrame | None:
    """個股三大法人買賣超股數（股）。支援上市與上櫃。"""
    ttl = get_settings()["update"]["price_refresh_minutes"] * 60
    c = None if force else CACHE.get("stock_inst", code, ttl)
    if c is None:
        start = (today_taipei() - timedelta(days=200)).isoformat()
        try:
            j = _http_json(f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={code}&start_date={start}{_fm_token()}")
            by_date: dict[str, dict[str, float]] = {}
            for r in j.get("data") or []:
                d = by_date.setdefault(r["date"], {"foreign": 0.0, "trust": 0.0, "dealer": 0.0})
                net = float((r.get("buy") or 0) - (r.get("sell") or 0))
                nm = r.get("name")
                if nm in ("Foreign_Investor", "Foreign_Dealer_Self"):
                    d["foreign"] += net
                elif nm == "Investment_Trust":
                    d["trust"] += net
                elif nm in ("Dealer_self", "Dealer_Hedging"):
                    d["dealer"] += net
            rows = [{"date": k, **v} for k, v in sorted(by_date.items())]
            c = CACHE.put("stock_inst", code, rows, "FinMind / TWSE·TPEx", rows[-1]["date"] if rows else None)
        except Exception as e:  # noqa: BLE001
            log.warning("stock_inst %s: %s", code, e)
            c = CACHE.get("stock_inst", code)
    if not c or not c["data"]:
        return None
    df = pd.DataFrame(c["data"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)


def load_stock_margin(code: str, force: bool = False) -> pd.DataFrame | None:
    """個股融資融券餘額（張）。"""
    ttl = get_settings()["update"]["price_refresh_minutes"] * 60
    c = None if force else CACHE.get("stock_margin", code, ttl)
    if c is None:
        start = (today_taipei() - timedelta(days=200)).isoformat()
        try:
            j = _http_json(f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMarginPurchaseShortSale&data_id={code}&start_date={start}{_fm_token()}")
            rows = [
                {
                    "date": r["date"],
                    "margin_balance": r.get("MarginPurchaseTodayBalance"),
                    "short_balance": r.get("ShortSaleTodayBalance"),
                }
                for r in j.get("data") or []
            ]
            c = CACHE.put("stock_margin", code, rows, "FinMind / TWSE·TPEx", rows[-1]["date"] if rows else None)
        except Exception as e:  # noqa: BLE001
            log.warning("stock_margin %s: %s", code, e)
            c = CACHE.get("stock_margin", code)
    if not c or not c["data"]:
        return None
    df = pd.DataFrame(c["data"])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index().astype(float)


# ============================================================
# 基本面（TWSE / TPEx OpenAPI）
# ============================================================
def fetch_fundamentals(force: bool = False) -> dict[str, dict]:
    """回傳 {code: {pe, pb, dividend_yield, revenue_yoy, revenue_mom, revenue_month}}。"""
    c = None if force else CACHE.get("fundamentals", "all", 6 * 3600)
    if c is not None:
        return c["data"]
    out: dict[str, dict] = {}
    try:
        for r in _http_json("https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"):
            out.setdefault(r["Code"], {}).update(
                pe=_num(r.get("PEratio")), pb=_num(r.get("PBratio")),
                dividend_yield=_num(r.get("DividendYield")), date=_roc_to_iso(r["Date"]))
    except Exception as e:  # noqa: BLE001
        log.warning("BWIBBU: %s", e)
    try:
        for r in _http_json("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"):
            out.setdefault(r["SecuritiesCompanyCode"], {}).update(
                pe=_num(r.get("PriceEarningRatio")), pb=_num(r.get("PriceBookRatio")),
                dividend_yield=_num(r.get("YieldRatio")), date=_roc_to_iso(r["Date"]))
    except Exception as e:  # noqa: BLE001
        log.warning("TPEx PE: %s", e)
    for url, code_key in [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap05_L", "公司代號"),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O", "公司代號"),
    ]:
        try:
            for r in _http_json(url):
                code = str(r.get(code_key, "")).strip()
                if not code:
                    continue
                ym = str(r.get("資料年月", ""))
                out.setdefault(code, {}).update(
                    revenue_yoy=_num(r.get("營業收入-去年同月增減(%)")),
                    revenue_mom=_num(r.get("營業收入-上月比較增減(%)")),
                    revenue_cum_yoy=_num(r.get("累計營業收入-前期比較增減(%)")),
                    revenue=_num(r.get("營業收入-當月營收")),
                    revenue_month=f"{int(ym[:-2]) + 1911}-{ym[-2:]}" if len(ym) >= 5 else None,
                    industry=r.get("產業別"))
        except Exception as e:  # noqa: BLE001
            log.warning("revenue %s: %s", url, e)
    if out:
        CACHE.put("fundamentals", "all", out, "TWSE/TPEx OpenAPI", date.today().isoformat())
        return out
    c = CACHE.get("fundamentals", "all")
    return c["data"] if c else {}
