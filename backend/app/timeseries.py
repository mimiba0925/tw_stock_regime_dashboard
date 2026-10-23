"""Time-series calculation layer：Change / Slope / Acceleration / Percentile / Z-score。

所有函式對缺失值保持誠實：資料不足回傳 None（前端顯示 N/A），絕不補 0。
"""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Literal

import numpy as np
import pandas as pd

from .config import get_settings

Normalize = Literal["level", "std", "none"]


def _f(x: Any) -> float | None:
    """轉成 JSON 安全 float；NaN / inf → None。"""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


# ---------------- 基本變化 ----------------
def change(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    return _f(s.iloc[-1] - s.iloc[-1 - n])


def pct_change(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    base = s.iloc[-1 - n]
    if base == 0 or pd.isna(base):
        return None
    return _f(s.iloc[-1] / base - 1)


# ---------------- Slope ----------------
def slope(values: np.ndarray | pd.Series, normalize: Normalize = "level") -> float | None:
    """最小平方法斜率（每期）。

    normalize:
      level → 除以 |平均值|，得「每日 % 變化」，適用價格/指數/成交量等正值序列
      std   → 除以標準差，適用法人買賣超等可能正負交錯的序列
    """
    y = np.asarray(pd.Series(values).dropna(), dtype=float)
    n = len(y)
    if n < 3:
        return None
    x = np.arange(n, dtype=float)
    x -= x.mean()
    b = float((x * (y - y.mean())).sum() / (x * x).sum())
    if normalize == "level":
        denom = abs(y.mean())
        return _f(b / denom) if denom > 0 else None
    if normalize == "std":
        denom = y.std()
        return _f(b / denom) if denom > 0 else 0.0
    return _f(b)


def rolling_slope(s: pd.Series, n: int, normalize: Normalize = "level") -> float | None:
    s = s.dropna()
    if len(s) < n:
        return None
    return slope(s.iloc[-n:], normalize)


def slope_series(s: pd.Series, n: int, normalize: Normalize = "level") -> pd.Series:
    return s.rolling(n, min_periods=n).apply(lambda w: slope(w, normalize) or 0.0, raw=True)


def acceleration(s: pd.Series, short: int = 5, medium: int = 20, normalize: Normalize = "level") -> float | None:
    a = rolling_slope(s, short, normalize)
    b = rolling_slope(s, medium, normalize)
    if a is None or b is None:
        return None
    return _f(a - b)


# ---------------- 歷史位置 ----------------
def percentile(s: pd.Series, n: int) -> float | None:
    """目前值在過去 n 期（含當期）中的百分位 0–100。"""
    s = s.dropna()
    if len(s) < max(5, min(n, 20)):
        return None
    w = s.iloc[-n:]
    cur = w.iloc[-1]
    less = (w < cur).sum()
    equal = (w == cur).sum()
    return _f(100.0 * (less + 0.5 * (equal - 1)) / max(len(w) - 1, 1))


def zscore(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) < max(5, min(n, 20)):
        return None
    w = s.iloc[-n:]
    sd = w.std()
    if not sd or pd.isna(sd):
        return None
    return _f((w.iloc[-1] - w.mean()) / sd)


# ---------------- 標籤 ----------------
def trend_label(slope_v: float | None, flat: float) -> str:
    if slope_v is None:
        return "N/A"
    if slope_v > flat:
        return "improving"
    if slope_v < -flat:
        return "deteriorating"
    return "neutral"


def accel_label(acc: float | None, flat: float) -> str:
    if acc is None:
        return "N/A"
    if acc > flat:
        return "accelerating"
    if acc < -flat:
        return "decelerating"
    return "stable"


def quality_of(s: pd.Series, estimated: bool = False, today: date | None = None) -> str:
    s = s.dropna()
    if s.empty:
        return "missing"
    stale_days = get_settings()["update"]["stale_after_days"]
    last = pd.Timestamp(s.index[-1]).date()
    today = today or datetime.now().date()
    # 週末不算延遲
    bdays = np.busday_count(last, today) if last < today else 0
    if bdays > stale_days:
        return "stale"
    return "estimated" if estimated else "available"


# ---------------- 完整 Metric 摘要 ----------------
def metric_summary(
    s: pd.Series,
    *,
    normalize: Normalize = "level",
    estimated: bool = False,
    source: str = "",
    unit: str = "",
    higher_is_better: bool = True,
    cumulative_flow: bool = False,
) -> dict[str, Any]:
    """產生單一 metric 的時間維度摘要。

    cumulative_flow=True：s 為每日流量（如外資買賣超），changes 以「N 日累計」表示，
    slope / percentile 則以 N 日累計序列計算。
    """
    cfg = get_settings()
    win = cfg["windows"]
    th = cfg["thresholds"]
    s = s.dropna().astype(float)
    if s.empty:
        return {"quality": "missing", "current": None, "source": source, "unit": unit}

    out: dict[str, Any] = {
        "current": _f(s.iloc[-1]),
        "as_of": str(pd.Timestamp(s.index[-1]).date()),
        "source": source,
        "unit": unit,
        "higher_is_better": higher_is_better,
        "quality": quality_of(s, estimated),
    }
    flat = th["flow_slope_flat"] if normalize == "std" else th["slope_flat"]

    if cumulative_flow:
        sums = {n: (_f(s.iloc[-n:].sum()) if len(s) >= n else None) for n in [1, 3, 5, 20, 60, 120, 250]}
        out["sums"] = {str(k): v for k, v in sums.items()}
        cum5 = s.rolling(5).sum()
        cum20 = s.rolling(20).sum()
        out["slopes"] = {
            "5": rolling_slope(cum5, 5, "std"),
            "20": rolling_slope(cum20, 20, "std"),
            "60": rolling_slope(s.cumsum(), 60, "std"),
        }
        out["acceleration"] = (
            _f(out["slopes"]["5"] - out["slopes"]["20"])
            if out["slopes"]["5"] is not None and out["slopes"]["20"] is not None else None
        )
        out["percentiles"] = {
            "20": percentile(cum20, 60),
            "60": percentile(cum20, 120),
            "250": percentile(cum20, 250),
        }
        out["zscores"] = {str(n): zscore(cum20, n) for n in win["zscores"]}
        out["flow_state"] = flow_state(s)
        out["trend"] = trend_label(out["slopes"]["20"], flat)
        out["accel"] = accel_label(out["acceleration"], th["flow_slope_flat"])
        spark = s.cumsum().iloc[-win["sparkline"]:]
    else:
        out["changes"] = {str(n): change(s, n) for n in win["changes"]}
        out["pct_changes"] = {str(n): pct_change(s, n) for n in win["changes"]}
        out["slopes"] = {str(n): rolling_slope(s, n, normalize) for n in win["slopes"]}
        out["acceleration"] = acceleration(s, 5, 20, normalize)
        out["percentiles"] = {str(n): percentile(s, n) for n in win["percentiles"]}
        out["zscores"] = {str(n): zscore(s, n) for n in win["zscores"]}
        out["trend"] = trend_label(out["slopes"]["20"], flat)
        out["accel"] = accel_label(out["acceleration"], th["accel_flat"] if normalize != "std" else flat)
        spark = s.iloc[-win["sparkline"]:]

    out["sparkline"] = [_f(v) for v in spark.values]
    return out


def flow_state(daily: pd.Series, short: int = 5, long: int = 20) -> str:
    """判斷法人行為：買超增加 / 買超減少 / 賣超增加 / 賣超減少。"""
    daily = daily.dropna()
    if len(daily) < long:
        return "N/A"
    recent = daily.iloc[-short:].mean()
    base = daily.iloc[-long:].mean()
    if recent >= 0:
        return "increasing_buying" if recent >= base else "decreasing_buying"
    return "increasing_selling" if recent <= base else "decreasing_selling"
