"""Service layer：串接 ingestion → indicators → time-series → scoring → regime → alerts。

計算結果以 Snapshot 快取（TTL = price_refresh_minutes），API 只讀 Snapshot。
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from . import alerts as AL
from . import indicators as I
from . import ingest as D
from . import scoring as S
from .config import get_settings, load_universe, load_watchlist, now_taipei, yahoo_symbol
from .regime import REGIME_ZH, classify, trend_state
from .timeseries import _f, metric_summary, percentile, pct_change, rolling_slope, quality_of

log = logging.getLogger("service")


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return _f(s.iloc[-1]) if len(s) else None


def _series_points(s: pd.Series, n: int) -> list[dict]:
    s = s.dropna().iloc[-n:]
    return [{"time": d.strftime("%Y-%m-%d"), "value": _f(v)} for d, v in s.items()]


# ============================================================
# Market features（可對任一歷史切片計算，以支援 Regime Change 比較）
# ============================================================
def market_features(M: pd.DataFrame) -> dict[str, Any]:
    c = M["close"]
    f: dict[str, Any] = {
        "close": _last(c), "ma20": _last(M["ma20"]), "ma60": _last(M["ma60"]), "ma120": _last(M["ma120"]),
        "ma20_slope": rolling_slope(M["ma20"], 20), "ma60_slope": rolling_slope(M["ma60"], 20),
        "ma120_slope": rolling_slope(M["ma120"], 20),
        "roc20": pct_change(c, 20), "roc5": pct_change(c, 5), "price_chg5": pct_change(c, 5),
        "rsi14": _last(M["rsi"]),
        "macd_hist_norm": (_last(M["macd_hist"]) / _last(c)) if _last(M["macd_hist"]) is not None else None,
        "accel": None,
        "drawdown": _last(M["drawdown"]),
        "vol_pct250": percentile(M["vol20"], 250),
    }
    s5, s20 = rolling_slope(c, 5), rolling_slope(c, 20)
    f["accel"] = None if s5 is None or s20 is None else s5 - s20
    f["dist_ma60"] = (f["close"] / f["ma60"] - 1) if f["ma60"] else None
    # breadth
    f["above_ma20"] = _last(M["above20"])
    f["above_ma60"] = _last(M["above60"])
    adv5 = M["adv"].iloc[-5:].sum()
    dec5 = M["dec"].iloc[-5:].sum()
    f["ad_ratio_5d"] = _f(adv5 / (adv5 + dec5)) if (adv5 + dec5) > 0 else None
    n_valid = _last(M["n_valid"])
    if n_valid:
        f["nh_nl_pct"] = _f((M["nh"].iloc[-5:].mean() - M["nl"].iloc[-5:].mean()) / n_valid * 100)
    a20 = M["above20"].dropna()
    f["above_ma20_chg5"] = _f(a20.iloc[-1] - a20.iloc[-6]) if len(a20) > 5 else None
    # liquidity
    tv = M["turnover"]
    f["turnover_pct60"] = percentile(tv, 60)
    ma20_tv = tv.rolling(20).mean()
    f["turnover_ratio_ma20"] = _f(tv.iloc[-5:].mean() / ma20_tv.iloc[-1]) if pd.notna(ma20_tv.iloc[-1]) else None
    # money flow
    for col in ["foreign", "trust", "total"]:
        s = M[col].dropna()
        if len(s) >= 20:
            f[f"{col}_cum20_pct"] = percentile(s.rolling(20).sum(), 250)
            f[f"{col}_cum5_pct"] = percentile(s.rolling(5).sum(), 250)
    fs = M["foreign"].dropna()
    f["foreign_slope"] = rolling_slope(fs.rolling(5).sum(), 20, "std") if len(fs) >= 25 else None
    # risk
    f["vix_pct250"] = percentile(M["vix"], 250) if "vix" in M else None
    f["usdtwd_chg20"] = pct_change(M["usdtwd"], 20) if "usdtwd" in M else None
    return f


def market_subscores(f: dict) -> dict[str, dict]:
    return {
        "trend": S.trend_score(f), "breadth": S.breadth_score(f), "momentum": S.momentum_score(f),
        "liquidity": S.liquidity_score(f), "money_flow": S.money_flow_score(f), "risk": S.risk_score(f),
    }


# ============================================================
# Snapshot
# ============================================================
class Snapshot:
    def __init__(self) -> None:
        self.built_at: datetime | None = None
        self.data: dict[str, Any] = {}
        self.prices: dict[str, pd.DataFrame] = {}
        self.meta: dict[str, dict] = {}


class DashboardService:
    def __init__(self) -> None:
        self.snap = Snapshot()
        self._lock = threading.Lock()

    # ---------------- public ----------------
    def get(self, force: bool = False) -> Snapshot:
        ttl = get_settings()["update"]["price_refresh_minutes"] * 60
        fresh = self.snap.built_at and (now_taipei() - self.snap.built_at).total_seconds() < ttl
        if fresh and not force:
            return self.snap
        with self._lock:
            fresh = self.snap.built_at and (now_taipei() - self.snap.built_at).total_seconds() < ttl
            if fresh and not force:
                return self.snap
            self.snap = self._build(force)
        return self.snap

    def invalidate(self) -> None:
        self.snap.built_at = None

    # ---------------- build ----------------
    def _build(self, force: bool) -> Snapshot:
        cfg = get_settings()
        snap = Snapshot()
        watch = load_watchlist()
        universe = load_universe()
        stocks: dict[str, dict] = {}
        for r in universe + watch:
            stocks.setdefault(r["symbol"], {**r, "in_universe": False, "in_watchlist": False})
        for r in universe:
            stocks[r["symbol"]]["in_universe"] = True
        for r in watch:
            stocks[r["symbol"]].update({**r, "in_watchlist": True,
                                         "in_universe": stocks[r["symbol"]]["in_universe"]})

        ext = cfg["data_source"]["external"]
        tw_jobs = ["TAIEX"] + list(stocks.keys())
        with ThreadPoolExecutor(max_workers=6) as ex:
            tw_futs = {k: ex.submit(D.fetch_tw_price, k, force) for k in tw_jobs}
            ext_futs = {k: ex.submit(D.fetch_external, k, force) for k in ext}
            prices = {k: f.result() for k, f in {**tw_futs, **ext_futs}.items()}
        twse_tv = D.fetch_twse_turnover(force=force)
        otc = D.fetch_tpex_index(force=force)
        fundamentals = D.fetch_fundamentals(force=force)

        taiex = prices.get("TAIEX")
        if taiex is None or taiex.empty:
            if twse_tv is not None:
                taiex = pd.DataFrame({"open": twse_tv["taiex"], "high": twse_tv["taiex"], "low": twse_tv["taiex"],
                                      "close": twse_tv["taiex"], "volume": np.nan})
                taiex.attrs["meta"] = {"source": "TWSE FMTQIK", "update_time": datetime.now().isoformat()}
            else:
                raise RuntimeError("無法取得加權指數資料")
        idx = taiex.index
        trading_days = [d.date() for d in idx]

        # ---------- breadth（樣本股）----------
        uni_syms = [s for s, r in stocks.items() if r["in_universe"] and prices.get(s) is not None]
        close_m = pd.DataFrame({s: prices[s]["close"] for s in uni_syms}).reindex(idx).ffill(limit=3)
        vol_m = pd.DataFrame({s: prices[s]["volume"] for s in uni_syms}).reindex(idx)
        diff = close_m.diff()
        value_m = close_m * vol_m
        valid = close_m.notna()
        ma20_m = close_m.rolling(20, min_periods=20).mean()
        ma60_m = close_m.rolling(60, min_periods=60).mean()
        ma120_m = close_m.rolling(120, min_periods=120).mean()
        hi250 = close_m.rolling(250, min_periods=120).max()
        lo250 = close_m.rolling(250, min_periods=120).min()

        def pct_true(cond: pd.DataFrame, base: pd.DataFrame) -> pd.Series:
            n = base.notna().sum(axis=1)
            return (cond.sum(axis=1) / n.replace(0, np.nan) * 100)

        B = pd.DataFrame(index=idx)
        B["adv"] = (diff > 0).sum(axis=1)
        B["dec"] = (diff < 0).sum(axis=1)
        B["unch"] = ((diff == 0) & valid).sum(axis=1)
        B["up_value"] = value_m.where(diff > 0).sum(axis=1)
        B["down_value"] = value_m.where(diff < 0).sum(axis=1)
        B["above20"] = pct_true(close_m > ma20_m, ma20_m)
        B["above60"] = pct_true(close_m > ma60_m, ma60_m)
        B["above120"] = pct_true(close_m > ma120_m, ma120_m)
        B["nh"] = ((close_m >= hi250) & hi250.notna()).sum(axis=1)
        B["nl"] = ((close_m <= lo250) & lo250.notna()).sum(axis=1)
        B["n_valid"] = valid.sum(axis=1)

        # ---------- market frame ----------
        c = taiex["close"]
        M = pd.DataFrame(index=idx)
        M["close"] = c
        for n in cfg["windows"]["ma"]:
            M[f"ma{n}"] = I.sma(c, n)
        M["rsi"] = I.rsi(c)
        M["macd_hist"] = I.macd(c)["hist"]
        M["drawdown"] = I.drawdown_from_high(c)
        M["vol20"] = I.realized_vol(c)
        turnover_src = "TWSE FMTQIK"
        if twse_tv is not None:
            M["turnover"] = twse_tv["turnover"].reindex(idx)
        if "turnover" in taiex.columns and taiex["turnover"].notna().any():
            M["turnover"] = M["turnover"].fillna(taiex["turnover"]) if "turnover" in M else taiex["turnover"]
            turnover_src = "FinMind / TWSE"
        if "turnover" not in M or M["turnover"].isna().all():
            M["turnover"] = taiex["volume"]
            turnover_src = "估計"
        M = M.join(B)
        trading_days_set = trading_days
        inst = D.load_market_institutional(trading_days_set, force=force)
        for col in ["foreign", "trust", "dealer", "total"]:
            M[col] = inst[col].reindex(idx) if inst is not None else np.nan
        if prices.get("VIX") is not None:
            M["vix"] = prices["VIX"]["close"].reindex(idx).ffill()
        if prices.get("USD/TWD") is not None:
            M["usdtwd"] = prices["USD/TWD"]["close"].reindex(idx).ffill()

        # ---------- scores now & lookback ----------
        lb = cfg["thresholds"]["regime_change_lookback"]
        f_now = market_features(M)
        subs_now = market_subscores(f_now)
        score_now = S.market_score(subs_now)

        # sector first (for dispersion)
        sectors = self._sectors(stocks, prices, close_m, value_m, c, ma20_m)
        r20s = [s["returns"]["20"] for s in sectors if s["returns"].get("20") is not None]
        dispersion = float(np.std(r20s)) if len(r20s) >= 3 else None

        def regime_ctx(f: dict, subs: dict, score: float | None) -> dict:
            return {
                "score": score, **{k: v["score"] for k, v in subs.items()},
                "long_uptrend": (f.get("ma60") or 0) > (f.get("ma120") or np.inf) and (f.get("ma60_slope") or 0) > 0,
                "roc5": f.get("roc5"), "volume_pct": f.get("turnover_pct60"),
                "breadth_chg5": f.get("above_ma20_chg5"), "dispersion": dispersion,
            }

        regime_now = classify(regime_ctx(f_now, subs_now, score_now))
        history = []
        for back in range(min(20, len(M) - 130), -1, -1):
            Mi = M.iloc[: len(M) - back]
            fi = market_features(Mi)
            si = market_subscores(fi)
            sc = S.market_score(si)
            history.append({"date": Mi.index[-1].strftime("%Y-%m-%d"), "score": sc,
                            **{k: v["score"] for k, v in si.items()},
                            "regime": classify(regime_ctx(fi, si, sc))["regime"]})
        prev = history[-1 - lb] if len(history) > lb else None
        as_of = idx[-1].strftime("%Y-%m-%d")

        # ---------- alerts ----------
        alert_list: list[dict] = []
        if prev and prev["regime"] != regime_now["regime"]:
            alert_list.append(AL.make_alert(
                category="market", kind="market_regime_change", severity="high",
                title=f"MARKET REGIME CHANGE：{REGIME_ZH[prev['regime']]} → {regime_now['label']}",
                reason="；".join(regime_now["reasons"]),
                metrics=[{"label": "Market Score", "from": f"{prev['score']:.0f}" if prev["score"] else "N/A",
                          "to": f"{score_now:.0f}" if score_now else "N/A"},
                         {"label": "Trend", "from": _fmt(prev["trend"]), "to": _fmt(subs_now["trend"]["score"])},
                         {"label": "Breadth", "from": _fmt(prev["breadth"]), "to": _fmt(subs_now["breadth"]["score"])}],
                conclusion="市場狀態改變，請檢視廣度與資金流是否同步。", as_of=as_of))
        alert_list += AL.detect_market_regime_changes(
            {"close": c, "ma60": M["ma60"], "above20": M["above20"], "nh": M["nh"], "nl": M["nl"],
             "foreign": M["foreign"], "turnover": M["turnover"], "vol": M["vol20"]}, as_of)
        alert_list += AL.detect_market_divergences(c, M["above20"], M["turnover"], M["foreign"], as_of)
        idx_ret5 = pct_change(c, 5)
        alert_list += AL.detect_sector_alerts(sectors, idx_ret5, as_of)

        # ---------- stocks ----------
        stock_rows, stock_details = self._stocks(stocks, prices, c, sectors, fundamentals, trading_days, as_of,
                                                 alert_list, force)

        # ---------- assemble ----------
        snap.prices = prices
        snap.data = {
            "as_of": as_of,
            "M": M, "B": B,
            "features": f_now, "subscores": subs_now, "score": score_now, "regime": regime_now,
            "score_history": history,
            "sectors": sectors, "dispersion": dispersion,
            "stocks": stock_rows, "stock_details": stock_details,
            "alerts": sorted(alert_list, key=lambda a: {"high": 0, "medium": 1, "low": 2}[a["severity"]]),
            "otc": otc, "taiex": taiex, "fundamentals": fundamentals,
            "turnover_src": turnover_src, "universe_size": len(uni_syms),
            "meta": {
                "taiex": taiex.attrs.get("meta", {}),
                "otc": {"source": "TPEx 櫃買指數", "data_timestamp": otc.index[-1].strftime("%Y-%m-%d") if otc is not None else None},
                "institutional": D.INST_LOADER.progress,
            },
        }
        snap.built_at = now_taipei()
        return snap

    # ---------------- sectors ----------------
    def _sectors(self, stocks, prices, close_m, value_m, index_close, ma20_m) -> list[dict]:
        out = []
        sector_map: dict[str, list[str]] = {}
        for s, r in stocks.items():
            if r["in_universe"] and s in close_m.columns:
                sector_map.setdefault(r["sector"], []).append(s)
        idx_rets = {n: pct_change(index_close, n) for n in [1, 5, 20, 60]}
        for name, syms in sector_map.items():
            rets = close_m[syms].pct_change(fill_method=None)
            eq = (1 + rets.mean(axis=1).fillna(0)).cumprod()
            r = {str(n): pct_change(eq, n) for n in [1, 5, 20, 60]}
            rs = {k: (None if v is None or idx_rets[int(k)] is None else v - idx_rets[int(k)]) for k, v in r.items()}
            above = ((close_m[syms] > ma20_m[syms]).iloc[-1].sum() / max(ma20_m[syms].iloc[-1].notna().sum(), 1)) * 100
            turnover = _f(value_m[syms].iloc[-5:].sum(axis=1).mean())
            momentum_shift = None
            if rs["5"] is not None and rs["20"] is not None:
                momentum_shift = rs["5"] - rs["20"] / 4
            out.append({
                "name": name, "count": len(syms), "symbols": syms,
                "returns": r, "relative_strength": rs,
                "breadth": _f(above), "turnover": turnover,
                "momentum_shift": _f(momentum_shift),
                "state": ("improving" if (momentum_shift or 0) > 0.005 else
                          "deteriorating" if (momentum_shift or 0) < -0.005 else "neutral"),
                "spark": [_f(v) for v in eq.iloc[-60:].values],
            })
        return out

    # ---------------- stocks ----------------
    def _stocks(self, stocks, prices, index_close, sectors, fundamentals, trading_days, as_of, alert_list, force: bool = False):
        sector_eq: dict[str, pd.Series] = {}
        for s in sectors:
            cm = pd.DataFrame({x: prices[x]["close"] for x in s["symbols"]}).reindex(index_close.index)
            sector_eq[s["name"]] = (1 + cm.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()

        lb = get_settings()["thresholds"]["regime_change_lookback"]
        rs_raw_now, rs_raw_prev, excess_all = {}, {}, {}
        for sym, r in stocks.items():
            df = prices.get(sym)
            if df is None or len(df) < 30:
                continue
            c = df["close"].reindex(index_close.index).ffill()
            ex = {str(n): (None if pct_change(c, n) is None or pct_change(index_close, n) is None
                           else pct_change(c, n) - pct_change(index_close, n))
                  for n in get_settings()["windows"]["rs_market"]}
            excess_all[sym] = ex
            rs_raw_now[sym] = S.rs_raw(ex)
            cp, ip = c.iloc[:-lb], index_close.iloc[:-lb]
            exp = {str(n): (None if pct_change(cp, n) is None or pct_change(ip, n) is None
                            else pct_change(cp, n) - pct_change(ip, n)) for n in [5, 20, 60, 120]}
            rs_raw_prev[sym] = S.rs_raw(exp)
        rs_now = S.rank_scores(rs_raw_now)
        rs_prev = S.rank_scores(rs_raw_prev)

        rows, details = [], {}
        for sym, r in stocks.items():
            if not r["in_watchlist"]:
                continue
            df = prices.get(sym)
            if df is None or len(df) < 30:
                rows.append({"symbol": sym, "name": r["name"], "sector": r["sector"], "market": r["market"],
                             "quality": "missing", "regime": None})
                continue
            det = self._stock_detail(sym, r, df, index_close, sector_eq.get(r["sector"]), excess_all.get(sym, {}),
                                     rs_now.get(sym), fundamentals.get(sym, {}), trading_days, force)
            details[sym] = det
            rows.append(det["row"])
            inst = D.load_stock_institutional(sym, trading_days, force=False)
            alert_list += AL.detect_stock_alerts(sym, r["name"], df, index_close, rs_now.get(sym),
                                                 rs_prev.get(sym), inst, as_of)
            if det["row"].get("regime_prev") and det["row"]["regime_prev"] != det["row"]["regime"]:
                alert_list.append(AL.make_alert(
                    category="stock", kind="stock_regime_change", severity="medium", symbol=sym,
                    title=f"{sym} {r['name']} REGIME CHANGE：{REGIME_ZH[det['row']['regime_prev']]} → {det['row']['regime_label']}",
                    reason=f"Stock Score {_fmt(det['row'].get('score_prev'))} → {_fmt(det['row']['score'])}",
                    as_of=as_of))
        rows.sort(key=lambda x: (int("".join(c for c in x["symbol"] if c.isdigit()) or 999999), x["symbol"]))
        return rows, details

    def _stock_features(self, df: pd.DataFrame, inst: pd.DataFrame | None, fund: dict) -> dict:
        c = df["close"]
        v = df["volume"]
        ma = {n: I.sma(c, n) for n in [20, 60, 120]}
        f = {
            "close": _last(c), "ma20": _last(ma[20]), "ma60": _last(ma[60]), "ma120": _last(ma[120]),
            "ma20_slope": rolling_slope(ma[20], 20),
            "dist_52wh": _last(I.drawdown_from_high(c)),
            "rsi14": _last(I.rsi(c)), "roc20": pct_change(c, 20), "price_chg5": pct_change(c, 5),
        }
        h = _last(I.macd(c)["hist"])
        f["macd_hist_norm"] = h / f["close"] if h is not None and f["close"] else None
        vma = v.rolling(20).mean()
        f["vol_ratio_ma20"] = _f(v.iloc[-5:].mean() / vma.iloc[-1]) if pd.notna(vma.iloc[-1]) and vma.iloc[-1] > 0 else None
        f["vol_pct60"] = percentile(v, 60)
        f["obv_slope"] = rolling_slope(I.obv(df), 20, "std")
        if inst is not None and len(inst) >= 5 and pd.notna(vma.iloc[-1]) and vma.iloc[-1] > 0:
            av = vma.iloc[-1]
            f["foreign_5d_ratio"] = _f(inst["foreign"].iloc[-5:].sum() / (av * 5))
            if len(inst) >= 20:
                f["foreign_20d_ratio"] = _f(inst["foreign"].iloc[-20:].sum() / (av * 20))
                f["trust_20d_ratio"] = _f(inst["trust"].iloc[-20:].sum() / (av * 20))
                tot = inst.sum(axis=1)
                f["inst_slope"] = rolling_slope(tot.rolling(5).sum(), 15, "std")
        f.update({k: fund.get(k) for k in ["pe", "pb", "dividend_yield", "revenue_yoy", "revenue_cum_yoy"]})
        return f

    def _stock_subscores(self, f: dict, rs: float | None) -> dict[str, dict]:
        return {
            "trend": S.stock_trend_score(f), "momentum": S.stock_momentum_score(f),
            "volume": S.stock_volume_score(f), "institutional": S.stock_chip_score(f),
            "relative_strength": {"score": rs, "components": {}},
            "fundamental": S.stock_fundamental_score(f),
        }

    def _stock_detail(self, sym, r, df, index_close, sector_eq, excess, rs, fund, trading_days, force: bool = False) -> dict:
        inst = D.load_stock_institutional(sym, trading_days, force=force)
        lb = get_settings()["thresholds"]["regime_change_lookback"]
        f = self._stock_features(df, inst, fund)
        subs = self._stock_subscores(f, rs)
        score = S.stock_score(subs)

        def ctx(ff, ss, sc):
            return {"score": sc, "trend": ss["trend"]["score"], "momentum": ss["momentum"]["score"],
                    "breadth": ss["relative_strength"]["score"],
                    "long_uptrend": (ff.get("ma60") or 0) > (ff.get("ma120") or np.inf) and (ff.get("ma20_slope") or 0) > -0.001,
                    "roc5": ff.get("price_chg5"), "volume_pct": ff.get("vol_pct60"), "breadth_chg5": None}

        reg = classify(ctx(f, subs, score), kind="stock")
        f_prev = self._stock_features(df.iloc[:-lb], inst.iloc[:-lb] if inst is not None and len(inst) > lb else None, fund)
        subs_prev = self._stock_subscores(f_prev, rs)
        score_prev = S.stock_score(subs_prev)
        reg_prev = classify(ctx(f_prev, subs_prev, score_prev), kind="stock")

        c = df["close"]
        c_al = c.reindex(index_close.index).ffill()
        vs_sector = {}
        if sector_eq is not None:
            for n in get_settings()["windows"]["rs_sector"]:
                a, b = pct_change(c_al, n), pct_change(sector_eq, n)
                vs_sector[str(n)] = None if a is None or b is None else a - b
        meta = df.attrs.get("meta", {})
        row = {
            "symbol": sym, "name": r["name"], "sector": r["sector"], "market": r["market"],
            "price": _last(c), "change": pct_change(c, 1), "change_abs": _f(c.iloc[-1] - c.iloc[-2]) if len(c) > 1 else None,
            "trend": subs["trend"]["score"], "momentum": subs["momentum"]["score"], "volume": subs["volume"]["score"],
            "chip": subs["institutional"]["score"], "rs": rs, "fundamental": subs["fundamental"]["score"],
            "score": score, "regime": reg["regime"], "regime_label": reg["label"], "regime_tone": reg["tone"],
            "regime_prev": reg_prev["regime"], "score_prev": score_prev,
            "spark": [_f(x) for x in c.iloc[-60:].values],
            "quality": quality_of(c), "as_of": c.index[-1].strftime("%Y-%m-%d"),
        }
        return {"row": row, "features": f, "subscores": subs, "regime": reg,
                "rs_market": excess, "rs_sector": vs_sector, "inst_available": inst is not None,
                "meta": meta, "fund": fund}


def _fmt(v: Any) -> str:
    return "N/A" if v is None else f"{v:.0f}"


SERVICE = DashboardService()
