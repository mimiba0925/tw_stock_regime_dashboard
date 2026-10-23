"""Scoring engine：所有分數 normalize 至 0–100，權重來自 config。

分數只是「資訊壓縮後的狀態」，不是預測，也不是買賣訊號。
缺失元件會被排除並重新分配權重（不視為 0）。
"""
from __future__ import annotations

from typing import Any

from .config import get_settings


def lin(x: float | None, lo: float, hi: float) -> float | None:
    """線性映射：x=lo → 0、x=hi → 100，超出範圍截斷。"""
    if x is None:
        return None
    if hi == lo:
        return 50.0
    v = (x - lo) / (hi - lo) * 100.0
    return max(0.0, min(100.0, v))


def boolean(x: bool | None) -> float | None:
    return None if x is None else (100.0 if x else 0.0)


def weighted(parts: dict[str, tuple[float | None, float]]) -> float | None:
    num = den = 0.0
    for score, w in parts.values():
        if score is None:
            continue
        num += score * w
        den += w
    return round(num / den, 1) if den > 0 else None


def _pack(parts: dict[str, tuple[float | None, float]]) -> dict[str, Any]:
    return {
        "score": weighted(parts),
        "components": {k: (None if v[0] is None else round(v[0], 1)) for k, v in parts.items()},
    }


def _gt(a: float | None, b: float | None) -> bool | None:
    return None if a is None or b is None else a > b


# ---------------- Market sub-scores ----------------
def trend_score(f: dict) -> dict:
    return _pack({
        "price_gt_ma20": (boolean(_gt(f.get("close"), f.get("ma20"))), 1),
        "ma20_gt_ma60": (boolean(_gt(f.get("ma20"), f.get("ma60"))), 1),
        "ma60_gt_ma120": (boolean(_gt(f.get("ma60"), f.get("ma120"))), 1),
        "ma20_slope": (lin(f.get("ma20_slope"), -0.003, 0.003), 1),
        "ma60_slope": (lin(f.get("ma60_slope"), -0.002, 0.002), 1),
        "dist_ma60": (lin(f.get("dist_ma60"), -0.08, 0.08), 1),
    })


def breadth_score(f: dict) -> dict:
    return _pack({
        "above_ma20": (f.get("above_ma20"), 1.0),
        "above_ma60": (f.get("above_ma60"), 1.0),
        "ad_ratio_5d": (lin(f.get("ad_ratio_5d"), 0.35, 0.65), 1.0),
        "nh_nl": (lin(f.get("nh_nl_pct"), -15, 15), 0.8),
        "above_ma20_chg5": (lin(f.get("above_ma20_chg5"), -20, 20), 0.7),
    })


def momentum_score(f: dict) -> dict:
    return _pack({
        "roc20": (lin(f.get("roc20"), -0.08, 0.08), 1),
        "rsi14": (lin(f.get("rsi14"), 30, 70), 1),
        "macd_hist": (lin(f.get("macd_hist_norm"), -0.005, 0.005), 1),
        "acceleration": (lin(f.get("accel"), -0.004, 0.004), 0.6),
    })


def liquidity_score(f: dict) -> dict:
    """量能分數：量增價漲最健康；量增價跌扣分。"""
    ratio = f.get("turnover_ratio_ma20")
    price_up = f.get("price_chg5")
    confirm = None
    if ratio is not None and price_up is not None:
        if price_up >= 0:
            confirm = lin(ratio, 0.7, 1.3)          # 上漲時量能越大越健康
        else:
            confirm = 100 - (lin(ratio, 0.7, 1.3) or 0)  # 下跌時放量為負面
    return _pack({
        "turnover_pct60": (f.get("turnover_pct60"), 1),
        "turnover_ratio_ma20": (lin(ratio, 0.6, 1.4), 0.8),
        "price_volume_confirm": (confirm, 1.2),
    })


def money_flow_score(f: dict) -> dict:
    return _pack({
        "foreign_cum20_pct": (f.get("foreign_cum20_pct"), 1.2),
        "foreign_cum5_pct": (f.get("foreign_cum5_pct"), 0.8),
        "trust_cum20_pct": (f.get("trust_cum20_pct"), 0.8),
        "total_cum5_pct": (f.get("total_cum5_pct"), 0.6),
        "foreign_slope": (lin(f.get("foreign_slope"), -0.3, 0.3), 0.6),
    })


def risk_score(f: dict) -> dict:
    """越高 = 風險越低 / 環境越健康。"""
    vol = f.get("vol_pct250")
    vix = f.get("vix_pct250")
    return _pack({
        "volatility": (None if vol is None else 100 - vol, 1.2),
        "drawdown": (lin(f.get("drawdown"), -0.20, 0.0), 1.0),
        "vix": (None if vix is None else 100 - vix, 0.6),
        "usdtwd_20d": (lin(f.get("usdtwd_chg20"), 0.03, -0.03), 0.5),  # 台幣升值(負值)為正面
    })


def market_score(subs: dict[str, dict]) -> float | None:
    w = get_settings()["market_score_weights"]
    return weighted({k: (subs[k]["score"] if k in subs else None, w[k]) for k in w})


# ---------------- Stock sub-scores ----------------
def stock_trend_score(f: dict) -> dict:
    return _pack({
        "price_gt_ma20": (boolean(_gt(f.get("close"), f.get("ma20"))), 1),
        "ma20_gt_ma60": (boolean(_gt(f.get("ma20"), f.get("ma60"))), 1),
        "ma60_gt_ma120": (boolean(_gt(f.get("ma60"), f.get("ma120"))), 0.8),
        "ma20_slope": (lin(f.get("ma20_slope"), -0.006, 0.006), 1),
        "dist_52wh": (lin(f.get("dist_52wh"), -0.30, 0.0), 0.8),
    })


def stock_momentum_score(f: dict) -> dict:
    return _pack({
        "rsi14": (lin(f.get("rsi14"), 30, 75), 1),
        "macd_hist": (lin(f.get("macd_hist_norm"), -0.01, 0.01), 1),
        "roc20": (lin(f.get("roc20"), -0.15, 0.15), 1),
    })


def stock_volume_score(f: dict) -> dict:
    ratio = f.get("vol_ratio_ma20")
    up = f.get("price_chg5")
    confirm = None
    if ratio is not None and up is not None:
        confirm = lin(ratio, 0.6, 1.6) if up >= 0 else 100 - (lin(ratio, 0.6, 1.6) or 0)
    return _pack({
        "obv_slope": (lin(f.get("obv_slope"), -0.5, 0.5), 1),
        "price_volume_confirm": (confirm, 1),
        "vol_pct60": (f.get("vol_pct60"), 0.5),
    })


def stock_chip_score(f: dict) -> dict:
    return _pack({
        # ratio = N 日法人淨買賣股數 / (20 日均量 × N)，即占成交量比例
        "foreign_5d": (lin(f.get("foreign_5d_ratio"), -0.10, 0.10), 1),
        "foreign_20d": (lin(f.get("foreign_20d_ratio"), -0.08, 0.08), 1),
        "trust_20d": (lin(f.get("trust_20d_ratio"), -0.04, 0.04), 0.8),
        "total_slope": (lin(f.get("inst_slope"), -0.3, 0.3), 0.6),
    })


def stock_fundamental_score(f: dict) -> dict:
    pe = f.get("pe")
    pe_score = None
    if pe is not None and pe > 0:
        pe_score = lin(pe, 45, 10)
    return _pack({
        "revenue_yoy": (lin(f.get("revenue_yoy"), -20, 40), 1.2),
        "revenue_cum_yoy": (lin(f.get("revenue_cum_yoy"), -15, 30), 1),
        "pe": (pe_score, 0.7),
        "pb": (lin(f.get("pb"), 8, 1), 0.4),
        "dividend_yield": (lin(f.get("dividend_yield"), 0, 6), 0.5),
    })


def rs_raw(excess: dict[str, float | None]) -> float | None:
    """加權超額報酬（Stock - TAIEX）。"""
    w = get_settings()["rs_score_weights"]
    num = den = 0.0
    for k, wt in w.items():
        v = excess.get(str(k))
        if v is None:
            continue
        num += v * wt
        den += wt
    return num / den if den else None


def rank_scores(values: dict[str, float | None]) -> dict[str, float | None]:
    """橫斷面百分位排名 → 0–100（RS Score）。"""
    valid = {k: v for k, v in values.items() if v is not None}
    n = len(valid)
    out: dict[str, float | None] = {k: None for k in values}
    if n == 0:
        return out
    if n == 1:
        k = next(iter(valid))
        out[k] = 50.0
        return out
    ordered = sorted(valid.items(), key=lambda kv: kv[1])
    for i, (k, _) in enumerate(ordered):
        out[k] = round(100.0 * i / (n - 1), 1)
    return out


def stock_score(subs: dict[str, dict]) -> float | None:
    w = get_settings()["stock_score_weights"]
    return weighted({k: (subs[k]["score"] if k in subs and subs[k] else None, w[k]) for k in w})
