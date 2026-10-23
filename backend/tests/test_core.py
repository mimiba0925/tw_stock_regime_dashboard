"""Deterministic unit tests：計算層、分數、Regime、背離偵測。"""
import numpy as np
import pandas as pd
import pytest

from app import alerts as AL
from app import indicators as I
from app import scoring as S
from app import timeseries as T
from app.regime import classify


def ser(values, start="2024-01-01"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


# ---------- moving average ----------
def test_sma():
    s = ser([1, 2, 3, 4, 5])
    out = I.sma(s, 3)
    assert out.isna().sum() == 2
    assert out.iloc[-1] == pytest.approx(4.0)


# ---------- change ----------
def test_change_and_pct_change():
    s = ser([100, 110, 121])
    assert T.change(s, 1) == pytest.approx(11)
    assert T.pct_change(s, 2) == pytest.approx(0.21)
    assert T.pct_change(s, 5) is None  # 資料不足 → None，不補 0


# ---------- slope ----------
def test_slope_linear_level_normalized():
    s = ser(np.arange(10, 20))  # 斜率 1，平均 14.5
    assert T.slope(s, "none") == pytest.approx(1.0)
    assert T.slope(s, "level") == pytest.approx(1 / 14.5)


def test_slope_flat_and_std():
    assert T.slope(ser([5] * 10), "level") == pytest.approx(0.0)
    assert T.slope(ser([5] * 10), "std") == 0.0


# ---------- acceleration ----------
def test_acceleration_positive_when_recent_steeper():
    vals = [100] * 15 + [100, 102, 104, 106, 108]
    acc = T.acceleration(ser(vals), 5, 20)
    assert acc is not None and acc > 0


def test_acceleration_negative_when_decelerating():
    vals = list(np.linspace(100, 140, 15)) + [140] * 5
    assert T.acceleration(ser(vals), 5, 20) < 0


# ---------- percentile ----------
def test_percentile_extremes():
    s = ser(list(range(1, 101)))
    assert T.percentile(s, 100) == pytest.approx(100.0)
    s2 = ser(list(range(100, 0, -1)))
    assert T.percentile(s2, 100) == pytest.approx(0.0)


def test_percentile_insufficient():
    assert T.percentile(ser([1, 2, 3]), 250) is None


# ---------- z-score ----------
def test_zscore():
    vals = [10] * 19 + [20]
    s = ser(vals)
    w = np.array(vals, dtype=float)
    assert T.zscore(s, 20) == pytest.approx((20 - w.mean()) / w.std(ddof=1))
    assert T.zscore(ser([5] * 30), 20) is None


# ---------- relative strength ----------
def test_rs_raw_and_rank():
    raw = S.rs_raw({"5": 0.01, "20": 0.02, "60": 0.03, "120": 0.04})
    assert raw == pytest.approx(0.15 * 0.01 + 0.30 * 0.02 + 0.30 * 0.03 + 0.25 * 0.04)
    ranks = S.rank_scores({"A": 0.1, "B": -0.1, "C": 0.0, "D": None})
    assert ranks == {"A": 100.0, "B": 0.0, "C": 50.0, "D": None}


def test_rs_missing_windows_reweighted():
    assert S.rs_raw({"20": 0.05}) == pytest.approx(0.05)
    assert S.rs_raw({}) is None


# ---------- scores ----------
def test_lin_clip():
    assert S.lin(0, -1, 1) == 50
    assert S.lin(5, -1, 1) == 100
    assert S.lin(-5, -1, 1) == 0
    assert S.lin(None, 0, 1) is None


def test_market_score_weights_and_missing():
    subs = {k: {"score": 80.0} for k in ["trend", "breadth", "momentum", "liquidity", "money_flow", "risk"]}
    assert S.market_score(subs) == pytest.approx(80.0)
    subs["money_flow"] = {"score": None}  # 缺失不算 0
    assert S.market_score(subs) == pytest.approx(80.0)
    subs2 = {**subs, "trend": {"score": 100.0}, "money_flow": {"score": 0.0}}
    # trend 0.25*100 + 0.15*0 + 其餘 0.60*80 = 73
    assert S.market_score(subs2) == pytest.approx(73.0)


def test_trend_score_bullish_alignment():
    f = {"close": 110, "ma20": 105, "ma60": 100, "ma120": 95, "ma20_slope": 0.003,
         "ma60_slope": 0.002, "dist_ma60": 0.08}
    assert S.trend_score(f)["score"] == pytest.approx(100.0)
    f_bear = {"close": 90, "ma20": 95, "ma60": 100, "ma120": 105, "ma20_slope": -0.003,
              "ma60_slope": -0.002, "dist_ma60": -0.10}
    assert S.trend_score(f_bear)["score"] == pytest.approx(0.0)


def test_stock_score():
    subs = {k: {"score": 50.0} for k in ["trend", "momentum", "volume", "institutional",
                                          "relative_strength", "fundamental"]}
    subs["trend"] = {"score": 100.0}
    # 0.20*100 + 0.80*50 = 60
    assert S.stock_score(subs) == pytest.approx(60.0)


# ---------- regime ----------
@pytest.mark.parametrize("ctx,expected", [
    ({"score": 82, "trend": 85, "breadth": 70, "momentum": 75}, "STRONG_BULL"),
    ({"score": 65, "trend": 70, "breadth": 55, "momentum": 60}, "BULL"),
    ({"score": 58, "trend": 62, "breadth": 50, "momentum": 35, "long_uptrend": True}, "BULL_PULLBACK"),
    ({"score": 15, "trend": 10, "breadth": 10, "momentum": 10}, "STRONG_BEAR"),
    ({"score": 30, "trend": 30, "breadth": 30, "momentum": 30}, "BEAR"),
    ({"score": 50, "trend": 45, "breadth": 55, "momentum": 62, "breadth_chg5": 5}, "RECOVERY"),
    ({"score": 52, "trend": 55, "breadth": 40, "momentum": 50, "dispersion": 0.06}, "ROTATION"),
    ({"score": 50, "trend": 55, "breadth": 55, "momentum": 50}, "NEUTRAL"),
    ({"score": 40, "trend": 45, "breadth": 45, "momentum": 45}, "WEAK"),
    ({"score": 20, "trend": 30, "breadth": 8, "momentum": 10, "roc5": -0.08, "volume_pct": 95}, "CAPITULATION"),
])
def test_regime_classification(ctx, expected):
    assert classify(ctx)["regime"] == expected


def test_regime_insufficient():
    r = classify({"score": None})
    assert r["regime"] == "NEUTRAL" and r.get("insufficient")


# ---------- divergence ----------
def test_price_breadth_divergence_detected():
    price = ser(np.linspace(100, 110, 30))
    breadth = ser(np.linspace(70, 40, 30))
    assert AL.price_up_other_down(price, breadth, window=10, other_is_level=True, other_flat=3)
    alerts = AL.detect_market_divergences(price, breadth, None, None, "2024-02-09")
    assert any(a["type"] == "price_breadth_divergence" for a in alerts)


def test_no_divergence_when_aligned():
    price = ser(np.linspace(100, 110, 30))
    breadth = ser(np.linspace(40, 70, 30))
    assert not AL.price_up_other_down(price, breadth, window=10, other_is_level=True)


def test_price_volume_and_institutional_divergence():
    price = ser(np.linspace(100, 110, 40))
    vol = ser(np.linspace(2000, 800, 40))
    foreign = ser([-1e9] * 40)
    types = {a["type"] for a in AL.detect_market_divergences(price, None, vol, foreign, "x")}
    assert {"price_volume_divergence", "price_institutional_divergence"} <= types


def test_flow_state():
    assert T.flow_state(ser([1] * 15 + [5] * 5)) == "increasing_buying"
    assert T.flow_state(ser([5] * 15 + [1] * 5)) == "decreasing_buying"
    assert T.flow_state(ser([-1] * 15 + [-5] * 5)) == "increasing_selling"
    assert T.flow_state(ser([-5] * 15 + [-1] * 5)) == "decreasing_selling"


def test_metric_summary_missing_is_not_zero():
    m = T.metric_summary(pd.Series(dtype=float))
    assert m["quality"] == "missing" and m["current"] is None
