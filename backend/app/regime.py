"""Regime engine：綜合多個面向決定市場 / 個股狀態，不依賴單一指標。"""
from __future__ import annotations

from typing import Any

from .config import get_settings

REGIMES = [
    "STRONG_BULL", "BULL", "BULL_PULLBACK", "ROTATION", "RECOVERY",
    "NEUTRAL", "WEAK", "BEAR", "STRONG_BEAR", "CAPITULATION",
]

REGIME_ZH = {
    "STRONG_BULL": "強勢多頭",
    "BULL": "多頭",
    "BULL_PULLBACK": "多頭回檔",
    "ROTATION": "類股輪動",
    "RECOVERY": "跌深復甦",
    "NEUTRAL": "中性盤整",
    "WEAK": "偏弱",
    "BEAR": "空頭",
    "STRONG_BEAR": "強勢空頭",
    "CAPITULATION": "恐慌拋售",
}

# 正向 / 負向 / 警示，對應前端固定顏色語意
REGIME_TONE = {
    "STRONG_BULL": "positive", "BULL": "positive", "BULL_PULLBACK": "caution",
    "ROTATION": "caution", "RECOVERY": "caution", "NEUTRAL": "neutral",
    "WEAK": "caution", "BEAR": "negative", "STRONG_BEAR": "negative", "CAPITULATION": "negative",
}


def _v(x: Any, default: float = 50.0) -> float:
    return default if x is None else float(x)


def classify(ctx: dict[str, Any], kind: str = "market") -> dict[str, Any]:
    """ctx keys：score, trend, breadth, momentum, money_flow, liquidity, risk,
    long_uptrend(bool), roc5, volume_pct, breadth_chg5, dispersion。"""
    r = get_settings()["regime"]
    score = ctx.get("score")
    if score is None:
        return {"regime": "NEUTRAL", "label": REGIME_ZH["NEUTRAL"], "tone": "neutral",
                "reasons": ["資料不足，暫列中性"], "insufficient": True}
    s = float(score)
    t = _v(ctx.get("trend"))
    b = _v(ctx.get("breadth"))
    m = _v(ctx.get("momentum"))
    roc5 = ctx.get("roc5")
    vol_pct = ctx.get("volume_pct")
    breadth_chg = ctx.get("breadth_chg5")
    disp = ctx.get("dispersion")
    long_up = ctx.get("long_uptrend")
    reasons: list[str] = []

    def done(name: str) -> dict[str, Any]:
        return {"regime": name, "label": REGIME_ZH[name], "tone": REGIME_TONE[name], "reasons": reasons}

    c = r["capitulation"]
    if (b <= c["breadth_max"] and roc5 is not None and roc5 <= c["roc5_max"]
            and vol_pct is not None and vol_pct >= c["volume_pct_min"]):
        reasons += [f"廣度僅 {b:.0f}", f"5 日跌幅 {roc5:.1%}", f"成交量位於 {vol_pct:.0f} 百分位"]
        return done("CAPITULATION")

    c = r["strong_bear"]
    if s <= c["score_max"] and t <= c["trend_max"]:
        reasons += [f"總分 {s:.0f}", f"趨勢 {t:.0f}"]
        return done("STRONG_BEAR")

    c = r["strong_bull"]
    if s >= c["score"] and t >= c["trend"] and b >= c["breadth"]:
        reasons += [f"總分 {s:.0f}", f"趨勢 {t:.0f}", f"廣度 {b:.0f}"]
        return done("STRONG_BULL")

    c = r["bull_pullback"]
    if long_up and t >= c["trend_min"] and m <= c["momentum_max"]:
        reasons += ["長期均線仍向上", f"動能降至 {m:.0f}"]
        return done("BULL_PULLBACK")

    c = r["bull"]
    if s >= c["score"] and t >= c["trend"]:
        reasons += [f"總分 {s:.0f}", f"趨勢 {t:.0f}"]
        return done("BULL")

    c = r["bear"]
    if s <= c["score_max"] and t <= c["trend_max"]:
        reasons += [f"總分 {s:.0f}", f"趨勢 {t:.0f}"]
        return done("BEAR")

    c = r["recovery"]
    if t <= c["trend_max"] and m >= c["momentum_min"] and (breadth_chg is None or breadth_chg > 0):
        reasons += [f"趨勢仍弱 {t:.0f}", f"動能回升 {m:.0f}"]
        return done("RECOVERY")

    c = r["rotation"]
    if (kind == "market" and c["score_min"] <= s <= c["score_max"] and b <= c["breadth_max"]
            and (disp is None or disp >= c["dispersion_min"])):
        reasons += [f"廣度偏窄 {b:.0f}", "類股報酬分歧" if disp is not None else "指數與廣度不一致"]
        return done("ROTATION")

    if s >= r["neutral"]["score_min"]:
        reasons.append(f"總分 {s:.0f} 位於中性區")
        return done("NEUTRAL")

    if s >= r["weak"]["score_min"]:
        reasons.append(f"總分 {s:.0f} 偏弱")
        return done("WEAK")

    reasons += [f"總分 {s:.0f}", f"趨勢 {t:.0f}"]
    return done("BEAR")


def trend_state(score: float | None) -> str:
    th = get_settings()["thresholds"]
    if score is None:
        return "N/A"
    if score >= th["trend_bull"]:
        return "bullish"
    if score <= th["trend_bear"]:
        return "bearish"
    return "neutral"
