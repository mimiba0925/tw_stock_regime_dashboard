"""REST API（FastAPI）。所有回應皆附 last_updated / source / quality 資訊。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import indicators as I
from . import ingest as D
from .config import get_settings, load_watchlist, save_watchlist
from .regime import REGIME_ZH, trend_state
from .service import SERVICE, _last, _series_points
from .timeseries import _f, metric_summary, percentile, pct_change, rolling_slope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = FastAPI(title="台股 Market Regime Dashboard API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def _snap(force: bool = False):
    try:
        return SERVICE.get(force)
    except Exception as e:  # noqa: BLE001
        logging.exception("snapshot build failed")
        raise HTTPException(503, f"資料建置失敗：{e}") from e


def _envelope(snap, payload: dict) -> dict:
    return {
        "as_of": snap.data["as_of"],
        "last_updated": snap.built_at.strftime("%Y-%m-%d %H:%M:%S") if snap.built_at else None,
        **payload,
    }


def _label_dir(v: float | None, flat: float = 0) -> str:
    if v is None:
        return "N/A"
    return "up" if v > flat else "down" if v < -flat else "flat"


# ============================================================
# Market
# ============================================================
def _index_block(df: pd.DataFrame | None, source: str) -> dict:
    if df is None or df.empty:
        return {"quality": "missing", "source": source}
    c = df["close"]
    m = metric_summary(c, source=source, unit="點")
    return {**m, "close": _last(c), "chg": _f(c.iloc[-1] - c.iloc[-2]) if len(c) > 1 else None,
            "chg_pct": pct_change(c, 1)}


def _answers(d: dict) -> list[dict]:
    """首頁 30 秒問答：把狀態轉成中文結論。"""
    subs, f, hist = d["subscores"], d["features"], d["score_history"]
    out = []
    reg = d["regime"]
    out.append({"q": "現在台股是多頭 / 空頭 / 中性？", "a": f"{reg['label']}（{reg['regime']}）", "tone": reg["tone"]})
    if len(hist) > 5 and hist[-1]["trend"] is not None and hist[-6]["trend"] is not None:
        dt = hist[-1]["trend"] - hist[-6]["trend"]
        tone = "positive" if dt > 3 else "negative" if dt < -3 else "neutral"
        out.append({"q": "趨勢正在變強還是變弱？",
                    "a": f"趨勢分數 5 日 {dt:+.0f}（{hist[-6]['trend']:.0f} → {hist[-1]['trend']:.0f}）"
                         + ("，加速中" if (f.get("accel") or 0) > 0.0005 else "，減速中" if (f.get("accel") or 0) < -0.0005 else ""),
                    "tone": tone})
    b = subs["breadth"]["score"]
    roc = f.get("roc5")
    a20c = f.get("above_ma20_chg5")
    if b is not None:
        supports = (roc or 0) >= 0 and (a20c or 0) >= 0 or (roc or 0) < 0 and (a20c or 0) < 0
        out.append({"q": "市場廣度支持指數嗎？",
                    "a": f"廣度分數 {b:.0f}；站上 MA20 {_pf(f.get('above_ma20'))}（5 日 {_pp(a20c)}）"
                         + ("，與指數同向" if supports else "，與指數背離"),
                    "tone": "positive" if supports and b >= 50 else "negative" if not supports else "caution"})
    M = d["M"]
    if M["foreign"].notna().sum() >= 5:
        fs = M["foreign"].dropna()
        ts = M["trust"].dropna()
        f5, t5 = fs.iloc[-5:].sum() / 1e8, ts.iloc[-5:].sum() / 1e8
        out.append({"q": "外資 / 投信正在買還是賣？",
                    "a": f"外資 5 日 {f5:+,.0f} 億、投信 5 日 {t5:+,.0f} 億",
                    "tone": "positive" if f5 + t5 > 0 else "negative"})
    else:
        out.append({"q": "外資 / 投信正在買還是賣？", "a": "法人資料下載中（N/A）", "tone": "neutral"})
    pv = _pv_state(M)
    if pv:
        out.append({"q": "成交量支持還是背離價格？", "a": pv["label"], "tone": pv["tone"]})
    secs = sorted([s for s in d["sectors"] if s["relative_strength"].get("20") is not None],
                  key=lambda s: -s["relative_strength"]["20"])
    if secs:
        out.append({"q": "哪些類股正在領導？", "a": "、".join(s["name"] for s in secs[:3]), "tone": "positive"})
        out.append({"q": "哪些類股正在轉弱？",
                    "a": "、".join(s["name"] for s in sorted(d["sectors"], key=lambda s: s["momentum_shift"] or 0)[:3]),
                    "tone": "negative"})
    rows = sorted([r for r in d["stocks"] if r.get("score") is not None], key=lambda r: -r["score"])
    if rows:
        out.append({"q": "我的自選股誰最強？",
                    "a": "、".join(f"{r['symbol']} {r['name']}（{r['score']:.0f}）" for r in rows[:3]), "tone": "positive"})
        changed = [r for r in rows if r.get("regime_prev") and r["regime_prev"] != r["regime"]]
        out.append({"q": "哪些股票正在發生 Regime Change？",
                    "a": "、".join(f"{r['symbol']} {REGIME_ZH[r['regime_prev']]}→{r['regime_label']}" for r in changed) or "無",
                    "tone": "caution" if changed else "neutral"})
    long_up = (f.get("ma60") or 0) > (f.get("ma120") or 1e18)
    below20 = (f.get("close") or 0) < (f.get("ma20") or 0)
    if long_up and (b or 0) >= 35:
        ans, tone = ("正常回檔：長期均線仍多頭排列、廣度未崩" if below20 else "多頭結構完整"), "positive" if not below20 else "caution"
    elif long_up:
        ans, tone = "需警戒：長期趨勢仍在但廣度明顯惡化，可能是結構改變前兆", "caution"
    else:
        ans, tone = "結構偏弱：MA60 已低於 MA120", "negative"
    out.append({"q": "正常回檔還是市場結構改變？", "a": ans, "tone": tone})
    return out


def _pf(v):
    return "N/A" if v is None else f"{v:.0f}%"


def _pp(v):
    return "N/A" if v is None else f"{v:+.0f}pp"


def _pv_state(M: pd.DataFrame, n: int = 5) -> dict | None:
    c, tv = M["close"].dropna(), M["turnover"].dropna()
    if len(c) <= 25 or len(tv) <= 25:
        return None
    p = pct_change(c, n)
    v = tv.iloc[-n:].mean() / tv.iloc[-25:-5].mean() - 1
    up_p, up_v = p >= 0, v >= 0
    key = ("up" if up_p else "down") + "_" + ("up" if up_v else "down")
    lab = {
        "up_up": ("價漲量增：健康上漲", "positive"),
        "up_down": ("價漲量縮：上漲動能不足", "caution"),
        "down_up": ("價跌量增：賣壓沉重", "negative"),
        "down_down": ("價跌量縮：惜售 / 量縮整理", "neutral"),
    }[key]
    return {"key": key, "label": lab[0], "tone": lab[1], "price_chg": _f(p), "volume_chg": _f(v)}


@app.get("/api/market/summary")
def market_summary():
    snap = _snap()
    d = snap.data
    return _envelope(snap, {
        "regime": d["regime"],
        "score": d["score"],
        "subscores": d["subscores"],
        "score_history": d["score_history"],
        "taiex": _index_block(d["taiex"], d["meta"]["taiex"].get("source", "Yahoo Finance")),
        "otc": _index_block(d["otc"], "TPEx 櫃買指數"),
        "answers": _answers(d),
        "trend_state": trend_state(d["subscores"]["trend"]["score"]),
        "data_status": {
            "institutional_progress": D.INST_LOADER.progress,
            "breadth_universe": d["universe_size"],
            "turnover_source": d["turnover_src"],
        },
        "disclaimer": "分數為資訊壓縮後的市場狀態，非預測，亦非買賣訊號。",
    })


def _trend_block(df: pd.DataFrame | None, source: str) -> dict:
    if df is None or df.empty:
        return {"quality": "missing", "source": source}
    c = df["close"]
    ma = {n: I.sma(c, n) for n in get_settings()["windows"]["ma"]}
    last = {f"ma{n}": _last(s) for n, s in ma.items()}
    close = _last(c)

    def dist(x):
        return None if x is None or close is None else close / x - 1

    slopes = {f"ma{n}": rolling_slope(ma[n], 20) for n in [20, 60, 120]}
    flat = get_settings()["thresholds"]["slope_flat"]

    def st(cond: bool | None, sl: float | None = None) -> str:
        if cond is None:
            return "N/A"
        if cond and (sl is None or sl > -flat):
            return "bullish"
        if not cond and (sl is None or sl < flat):
            return "bearish"
        return "neutral"

    hi = c.iloc[-250:].max()
    checks = [
        {"label": "收盤 > MA20", "state": st(None if last["ma20"] is None else close > last["ma20"], slopes["ma20"]),
         "detail": f"距離 {dist(last['ma20']):+.2%}" if last["ma20"] else "N/A"},
        {"label": "MA20 > MA60", "state": st(None if last["ma60"] is None else last["ma20"] > last["ma60"], slopes["ma60"]),
         "detail": f"MA20 斜率 {slopes['ma20']:+.3%}/日" if slopes["ma20"] is not None else "N/A"},
        {"label": "MA60 > MA120", "state": st(None if last["ma120"] is None else last["ma60"] > last["ma120"], slopes["ma120"]),
         "detail": f"MA60 斜率 {slopes['ma60']:+.3%}/日" if slopes["ma60"] is not None else "N/A"},
        {"label": "MA120 斜率", "state": st(None if slopes["ma120"] is None else slopes["ma120"] > 0),
         "detail": f"{slopes['ma120']:+.3%}/日" if slopes["ma120"] is not None else "N/A"},
    ]
    n = 250
    chart = {"close": _series_points(c, n), **{f"ma{k}": _series_points(v, n) for k, v in ma.items()}}
    if {"open", "high", "low"}.issubset(df.columns):
        dd = df.dropna(subset=["close"]).iloc[-n:]
        chart["candles"] = [{"time": t.strftime("%Y-%m-%d"), "open": _f(r.open), "high": _f(r.high),
                             "low": _f(r.low), "close": _f(r.close)} for t, r in dd.iterrows()]
    return {
        "close": close, **last,
        "dist_ma20": dist(last["ma20"]), "dist_ma60": dist(last["ma60"]),
        "dist_52w_high": _f(close / hi - 1) if close else None,
        "slopes": slopes,
        "ma20_vs_ma60": dist(None) if False else (None if not last["ma60"] else last["ma20"] / last["ma60"] - 1),
        "ma60_vs_ma120": None if not last["ma120"] else last["ma60"] / last["ma120"] - 1,
        "checks": checks, "chart": chart, "source": source,
    }


@app.get("/api/market/trend")
def market_trend():
    snap = _snap()
    d = snap.data
    return _envelope(snap, {
        "score": d["subscores"]["trend"], "state": trend_state(d["subscores"]["trend"]["score"]),
        "taiex": _trend_block(d["taiex"], d["meta"]["taiex"].get("source", "Yahoo Finance")),
        "otc": _trend_block(d["otc"], "TPEx 櫃買指數"),
    })


@app.get("/api/market/breadth")
def market_breadth():
    snap = _snap()
    d = snap.data
    B = d["B"]
    src = f"樣本股 {d['universe_size']} 檔（估計）"
    ad_ratio = B["adv"] / B["dec"].replace(0, np.nan)
    total_val = B["up_value"] + B["down_value"]
    nhnl = B["nh"] / B["nl"].replace(0, np.nan)
    metrics = {
        "advance": metric_summary(B["adv"].astype(float), normalize="std", estimated=True, source=src, unit="家"),
        "decline": metric_summary(B["dec"].astype(float), normalize="std", estimated=True, source=src, unit="家",
                                  higher_is_better=False),
        "ad_ratio": metric_summary(ad_ratio, normalize="std", estimated=True, source=src, unit="x"),
        "ad_volume": metric_summary((B["up_value"] / total_val.replace(0, np.nan)) * 100, normalize="std",
                                    estimated=True, source=src, unit="%"),
        "above_ma20": metric_summary(B["above20"], normalize="std", estimated=True, source=src, unit="%"),
        "above_ma60": metric_summary(B["above60"], normalize="std", estimated=True, source=src, unit="%"),
        "above_ma120": metric_summary(B["above120"], normalize="std", estimated=True, source=src, unit="%"),
        "new_high": metric_summary(B["nh"].astype(float), normalize="std", estimated=True, source=src, unit="家"),
        "new_low": metric_summary(B["nl"].astype(float), normalize="std", estimated=True, source=src, unit="家",
                                  higher_is_better=False),
        "nh_nl_ratio": metric_summary(nhnl, normalize="std", estimated=True, source=src, unit="x"),
    }
    chg5 = d["features"].get("above_ma20_chg5")
    th = get_settings()["thresholds"]["breadth_change_flat"]
    state = "N/A" if chg5 is None else "improving" if chg5 > th else "deteriorating" if chg5 < -th else "neutral"
    return _envelope(snap, {
        "score": d["subscores"]["breadth"], "state": state, "metrics": metrics,
        "chart": {"above20": _series_points(B["above20"], 250), "above60": _series_points(B["above60"], 250),
                  "taiex": _series_points(d["M"]["close"], 250)},
        "note": "廣度以 config/universe.csv 樣本股計算，屬估計值；可擴充樣本股提高代表性。",
    })


@app.get("/api/market/flow")
def market_flow():
    snap = _snap()
    d = snap.data
    M = d["M"]
    names = {"foreign": "外資", "trust": "投信", "dealer": "自營商", "total": "三大法人合計"}
    out = {}
    for k, label in names.items():
        s = M[k].dropna()
        m = metric_summary(s, normalize="std", cumulative_flow=True, source="TWSE BFI82U", unit="元")
        m["label"] = label
        m["bars"] = _series_points(s, 60)
        out[k] = m
    return _envelope(snap, {"score": d["subscores"]["money_flow"], "flows": out,
                            "progress": D.INST_LOADER.progress})


@app.get("/api/market/liquidity")
def market_liquidity():
    snap = _snap()
    d = snap.data
    M, B = d["M"], d["B"]
    tv = M["turnover"]
    total = B["up_value"] + B["down_value"]
    vp60 = percentile(tv, 60)
    th = get_settings()["thresholds"]
    level = "N/A" if vp60 is None else "high" if vp60 >= th["volume_high_pct"] else "low" if vp60 <= th["volume_low_pct"] else "normal"
    # 近 20 日價量象限歷史
    quad = []
    c = M["close"]
    for i in range(max(26, len(M) - 20), len(M) + 1):
        st = _pv_state(M.iloc[:i])
        if st:
            quad.append({"date": M.index[i - 1].strftime("%Y-%m-%d"), **st})
    return _envelope(snap, {
        "score": d["subscores"]["liquidity"],
        "turnover": metric_summary(tv, source=d["turnover_src"], unit="元"),
        "avg5": _f(tv.iloc[-5:].mean()), "avg20": _f(tv.iloc[-20:].mean()),
        "ratio_ma20": _f(tv.iloc[-1] / tv.iloc[-20:].mean()) if tv.notna().sum() >= 20 else None,
        "up_volume_ratio": _f(B["up_value"].iloc[-1] / total.iloc[-1]) if total.iloc[-1] else None,
        "down_volume_ratio": _f(B["down_value"].iloc[-1] / total.iloc[-1]) if total.iloc[-1] else None,
        "percentiles": {"20": percentile(tv, 20), "60": vp60, "250": percentile(tv, 250)},
        "level": level, "pv_state": _pv_state(M), "pv_history": quad,
        "bars": _series_points(tv, 120),
    })


@app.get("/api/market/risk")
def market_risk():
    snap = _snap()
    d = snap.data
    M = d["M"]
    ext = []
    for name in get_settings()["data_source"]["external"]:
        df = snap.prices.get(name)
        if df is None:
            ext.append({"name": name, "quality": "missing"})
            continue
        c = df["close"]
        ext.append({"name": name, "close": _last(c), "chg1": pct_change(c, 1), "chg5": pct_change(c, 5),
                    "chg20": pct_change(c, 20), "percentile250": percentile(c, 250),
                    "spark": [_f(x) for x in c.iloc[-60:].values],
                    "as_of": c.index[-1].strftime("%Y-%m-%d")})
    return _envelope(snap, {
        "score": d["subscores"]["risk"],
        "volatility": metric_summary(M["vol20"], source="TAIEX 20D 實現波動度", unit="%", higher_is_better=False),
        "drawdown": _f(M["drawdown"].iloc[-1]),
        "external": ext,
        "note": "全球市場僅作為外部風險背景（External Risk Context）。",
    })


# ============================================================
# Sectors
# ============================================================
@app.get("/api/sectors")
def sectors():
    snap = _snap()
    return _envelope(snap, {"sectors": snap.data["sectors"], "dispersion": snap.data["dispersion"],
                            "note": "類股報酬為樣本股等權重；Treemap 面積 = 近 5 日平均成交值。"})


# ============================================================
# Stocks
# ============================================================
class WatchItem(BaseModel):
    symbol: str
    name: str | None = None
    market: str = "TWSE"
    sector: str | None = None


@app.get("/api/stocks/watchlist")
def watchlist():
    snap = _snap()
    return _envelope(snap, {"rows": snap.data["stocks"], "csv": get_settings()["data_source"]["watchlist_csv"]})


@app.post("/api/stocks/watchlist")
def add_watch(item: WatchItem):
    rows = load_watchlist()
    if any(r["symbol"] == item.symbol for r in rows):
        raise HTTPException(409, "已在自選股中")
    rows.append({"symbol": item.symbol.strip(), "name": item.name or item.symbol,
                 "market": item.market.upper(), "sector": item.sector or "未分類"})
    save_watchlist(rows)
    SERVICE.invalidate()
    return {"ok": True, "count": len(rows)}


@app.delete("/api/stocks/watchlist/{symbol}")
def del_watch(symbol: str):
    rows = [r for r in load_watchlist() if r["symbol"] != symbol]
    save_watchlist(rows)
    SERVICE.invalidate()
    return {"ok": True, "count": len(rows)}


def _detail(symbol: str):
    snap = _snap()
    det = snap.data["stock_details"].get(symbol)
    if det is None:
        raise HTTPException(404, f"{symbol} 不在自選股名單（請加入 watchlist.csv）")
    return snap, det


@app.get("/api/stocks/{symbol}")
def stock(symbol: str):
    snap, det = _detail(symbol)
    return _envelope(snap, {k: det[k] for k in ["row", "features", "subscores", "regime", "rs_market", "rs_sector",
                                                 "inst_available", "meta"]})


@app.get("/api/stocks/{symbol}/trend")
def stock_trend(symbol: str):
    snap, det = _detail(symbol)
    df = snap.prices[symbol]
    c, v = df["close"], df["volume"]
    n = 250
    m = I.macd(c)
    vma = v.rolling(20).mean()
    blk = _trend_block(df, det["meta"].get("source", "Yahoo Finance"))
    ix = snap.data["M"]["close"]
    c_al = c.reindex(ix.index).ffill()
    rel = (c_al / c_al.iloc[-n]) / (ix / ix.iloc[-n]) * 100 if len(ix) > n else None
    return _envelope(snap, {
        **blk,
        "volume": [{"time": t.strftime("%Y-%m-%d"), "value": _f(x), "up": bool(c.loc[t] >= o)}
                   for t, x, o in zip(df.index[-n:], v.iloc[-n:], df["open"].iloc[-n:])],
        "momentum": {
            "rsi": _series_points(I.rsi(c), n), "macd": _series_points(m["macd"], n),
            "signal": _series_points(m["signal"], n), "hist": _series_points(m["hist"], n),
            "roc20": _series_points(I.roc(c, 20) * 100, n),
            "rsi_now": _last(I.rsi(c)), "roc20_now": pct_change(c, 20), "macd_hist_now": _last(m["hist"]),
        },
        "volume_metrics": {
            "vol_ratio_ma20": _f(v.iloc[-1] / vma.iloc[-1]) if pd.notna(vma.iloc[-1]) and vma.iloc[-1] else None,
            "obv": _series_points(I.obv(df), n), "atr": _last(I.atr(df)),
            "atr_pct": _f(_last(I.atr(df)) / c.iloc[-1]),
            "percentiles": {"20": percentile(v, 20), "60": percentile(v, 60), "250": percentile(v, 250)},
        },
        "relative": _series_points(rel, n) if rel is not None else [],
        "rs_market": det["rs_market"], "rs_sector": det["rs_sector"],
        "price_metric": metric_summary(c, source="Yahoo Finance", unit="元"),
    })


@app.get("/api/stocks/{symbol}/flow")
def stock_flow(symbol: str):
    snap, det = _detail(symbol)
    days = [d.date() for d in snap.data["M"].index]
    inst = D.load_stock_institutional(symbol, days)
    if inst is None:
        return _envelope(snap, {"available": False, "reason": "法人資料暫不可用（N/A）"})
    out = {}
    for k, lab in [("foreign", "外資"), ("trust", "投信"), ("dealer", "自營商")]:
        m = metric_summary(inst[k] / 1000, normalize="std", cumulative_flow=True, source="FinMind / TWSE·TPEx", unit="張")
        m["label"] = lab
        m["bars"] = _series_points(inst[k] / 1000, 60)
        out[k] = m
    mg = D.load_stock_margin(symbol)
    positioning = {}
    if mg is not None and not mg.empty:
        positioning["margin"] = metric_summary(mg["margin_balance"], normalize="std", source="FinMind / TWSE·TPEx", unit="張", higher_is_better=False)
        positioning["short"] = metric_summary(mg["short_balance"], normalize="std", source="FinMind / TWSE·TPEx", unit="張")
    return _envelope(snap, {"available": True, "flows": out, "positioning": positioning, "score": det["subscores"]["institutional"]})


@app.get("/api/stocks/{symbol}/fundamentals")
def stock_fund(symbol: str):
    snap, det = _detail(symbol)
    fund = det["fund"]
    # 同業（樣本股）歷史位置以橫斷面百分位替代
    allf = snap.data["fundamentals"]
    def xpct(key):
        v = fund.get(key)
        vals = [x.get(key) for x in allf.values() if x.get(key) is not None]
        if v is None or not vals:
            return None
        return _f((np.array(vals) < v).mean() * 100)
    items = [
        {"key": "revenue_yoy", "label": "月營收 YoY", "value": fund.get("revenue_yoy"), "unit": "%"},
        {"key": "revenue_cum_yoy", "label": "累計營收 YoY", "value": fund.get("revenue_cum_yoy"), "unit": "%"},
        {"key": "revenue_mom", "label": "月營收 MoM", "value": fund.get("revenue_mom"), "unit": "%"},
        {"key": "pe", "label": "本益比 PE", "value": fund.get("pe"), "unit": "x"},
        {"key": "pb", "label": "股價淨值比 PB", "value": fund.get("pb"), "unit": "x"},
        {"key": "dividend_yield", "label": "殖利率", "value": fund.get("dividend_yield"), "unit": "%"},
        {"key": "eps_yoy", "label": "EPS YoY", "value": None, "unit": "%"},
        {"key": "roe", "label": "ROE", "value": None, "unit": "%"},
        {"key": "gross_margin", "label": "毛利率", "value": None, "unit": "%"},
    ]
    for it in items:
        it["market_percentile"] = xpct(it["key"])
        it["quality"] = "available" if it["value"] is not None else "missing"
    return _envelope(snap, {"items": items, "revenue_month": fund.get("revenue_month"), "as_of_valuation": fund.get("date"),
                            "score": det["subscores"]["fundamental"],
                            "note": "EPS / ROE / 毛利率需季報資料源，第一版顯示 N/A。百分位為全市場橫斷面位置。"})


# ============================================================
# Alerts / status
# ============================================================
@app.get("/api/alerts")
def alerts(category: str | None = None):
    snap = _snap()
    a = snap.data["alerts"]
    if category:
        a = [x for x in a if x["category"] == category]
    return _envelope(snap, {"alerts": a})


@app.get("/api/status")
def status():
    snap = SERVICE.snap
    return {"built_at": snap.built_at.isoformat() if snap.built_at else None,
            "institutional": D.INST_LOADER.progress, "now": datetime.now().isoformat(timespec="seconds")}


@app.post("/api/refresh")
def refresh():
    snap = _snap(force=True)
    return {"ok": True, "last_updated": snap.built_at.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/config/ui")
def ui_config():
    cfg = get_settings()
    return {"title": cfg["app"]["title"], "market_weights": cfg["market_score_weights"],
            "stock_weights": cfg["stock_score_weights"], "regimes": REGIME_ZH}
