"""Alert engine：背離偵測 + Regime Change 偵測。純函式，輸入序列、輸出 alert dict。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

from .config import get_settings


def _ret(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n or s.iloc[-1 - n] == 0:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1)


def _diff(s: pd.Series, n: int) -> float | None:
    s = s.dropna()
    if len(s) <= n:
        return None
    return float(s.iloc[-1] - s.iloc[-1 - n])


def make_alert(*, category: str, kind: str, severity: str, title: str, reason: str,
               symbol: str = "TAIEX", metrics: list[dict] | None = None,
               conclusion: str = "", as_of: str | None = None) -> dict[str, Any]:
    return {
        "time": as_of or datetime.now().strftime("%Y-%m-%d"),
        "category": category, "type": kind, "symbol": symbol, "severity": severity,
        "title": title, "reason": reason, "metrics": metrics or [], "conclusion": conclusion,
    }


# ---------------- Divergence ----------------
def price_up_other_down(price: pd.Series, other: pd.Series, *, window: int | None = None,
                        min_move: float | None = None, other_is_level: bool = False,
                        other_flat: float = 0.0) -> bool:
    """價格上漲（> min_move）但 other 下降。other_is_level=True 時以差值判斷（如廣度百分比）。"""
    th = get_settings()["thresholds"]
    window = window or th["divergence_window"]
    min_move = th["divergence_price_min"] if min_move is None else min_move
    pr = _ret(price, window)
    oc = _diff(other, window) if other_is_level else _ret(other, window)
    if pr is None or oc is None:
        return False
    return pr > min_move and oc < -other_flat


def detect_market_divergences(close: pd.Series, above20: pd.Series | None, turnover: pd.Series | None,
                              foreign: pd.Series | None, as_of: str) -> list[dict]:
    th = get_settings()["thresholds"]
    w = th["divergence_window"]
    out: list[dict] = []
    pr = _ret(close, w)
    if above20 is not None and price_up_other_down(close, above20, other_is_level=True,
                                                   other_flat=th["breadth_change_flat"]):
        out.append(make_alert(
            category="market", kind="price_breadth_divergence", severity="high",
            title="空頭廣度背離（指數 ↑ 廣度 ↓）",
            reason=f"加權指數 {w} 日 {pr:+.1%}，站上 MA20 比例卻下降 {_diff(above20, w):.0f} 個百分點",
            metrics=[{"label": "Above MA20", "from": _fmt_pct(above20.dropna().iloc[-1 - w]),
                      "to": _fmt_pct(above20.dropna().iloc[-1])}],
            conclusion="指數上漲集中於少數權值股，市場參與度不足。", as_of=as_of))
    if turnover is not None:
        t5 = turnover.rolling(5).mean()
        if price_up_other_down(close, t5, other_flat=0.10):
            out.append(make_alert(
                category="market", kind="price_volume_divergence", severity="medium",
                title="量價背離：弱勢反彈（價 ↑ 量 ↓）",
                reason=f"指數 {w} 日 {pr:+.1%}，5 日均量較 {w} 日前減少 {_ret(t5, w):.0%}",
                conclusion="上漲缺乏量能支撐。", as_of=as_of))
    if foreign is not None and len(foreign.dropna()) >= w and pr is not None:
        fsum = float(foreign.iloc[-w:].sum())
        if pr > th["divergence_price_min"] and fsum < 0:
            out.append(make_alert(
                category="market", kind="price_institutional_divergence", severity="medium",
                title="法人背離（指數 ↑ 外資賣超）",
                reason=f"指數 {w} 日 {pr:+.1%}，外資同期累計賣超 {fsum / 1e8:,.0f} 億",
                conclusion="上漲並非由外資資金推動。", as_of=as_of))
    return out


def _fmt_pct(v: float | None) -> str:
    return "N/A" if v is None or pd.isna(v) else f"{v:.0f}%"


# ---------------- Regime change ----------------
def detect_market_regime_changes(f: dict[str, pd.Series], as_of: str) -> list[dict]:
    """f: close, ma60, above20, nh, nl, foreign, turnover, vol"""
    th = get_settings()["thresholds"]
    lb = th["regime_change_lookback"]
    out: list[dict] = []
    close, ma60 = f.get("close"), f.get("ma60")
    if close is not None and ma60 is not None:
        c, m = close.dropna(), ma60.reindex(close.index)
        if len(c) > lb and pd.notna(m.iloc[-1]) and pd.notna(m.iloc[-1 - lb]):
            was_above = c.iloc[-1 - lb] > m.iloc[-1 - lb]
            now_above = c.iloc[-1] > m.iloc[-1]
            if was_above and not now_above:
                out.append(make_alert(category="market", kind="trend_reversal", severity="high",
                                      title="REGIME CHANGE：加權指數跌破 MA60",
                                      reason=f"收盤 {c.iloc[-1]:,.0f} < MA60 {m.iloc[-1]:,.0f}",
                                      conclusion="中期趨勢轉弱，需觀察是否為結構改變。", as_of=as_of))
            elif not was_above and now_above:
                out.append(make_alert(category="market", kind="trend_reversal", severity="medium",
                                      title="REGIME CHANGE：加權指數站回 MA60",
                                      reason=f"收盤 {c.iloc[-1]:,.0f} > MA60 {m.iloc[-1]:,.0f}",
                                      conclusion="中期趨勢修復。", as_of=as_of))
    a20 = f.get("above20")
    if a20 is not None and len(a20.dropna()) > lb:
        s = a20.dropna()
        d = s.iloc[-1] - s.iloc[-1 - lb]
        if d <= -15:
            out.append(make_alert(category="market", kind="breadth_deterioration", severity="high",
                                  title="廣度快速惡化",
                                  reason=f"Above MA20 從 {s.iloc[-1 - lb]:.0f}% 降至 {s.iloc[-1]:.0f}%",
                                  metrics=[{"label": "Above MA20", "from": f"{s.iloc[-1 - lb]:.0f}%",
                                            "to": f"{s.iloc[-1]:.0f}%"}], as_of=as_of))
        elif d >= 15:
            out.append(make_alert(category="market", kind="breadth_expansion", severity="low",
                                  title="廣度擴張",
                                  reason=f"Above MA20 從 {s.iloc[-1 - lb]:.0f}% 升至 {s.iloc[-1]:.0f}%",
                                  as_of=as_of))
    nh, nl = f.get("nh"), f.get("nl")
    if nh is not None and nl is not None and len(nh.dropna()) > lb:
        if nl.iloc[-1] > nh.iloc[-1] and nl.iloc[-1 - lb] <= nh.iloc[-1 - lb]:
            out.append(make_alert(category="market", kind="breadth_deterioration", severity="medium",
                                  title="新低家數 > 新高家數",
                                  reason=f"52W 新高 {nh.iloc[-1]:.0f} / 新低 {nl.iloc[-1]:.0f}", as_of=as_of))
    fr = f.get("foreign")
    if fr is not None and len(fr.dropna()) >= 20 + lb:
        c20 = fr.rolling(20).sum()
        if c20.iloc[-1 - lb] > 0 > c20.iloc[-1]:
            out.append(make_alert(category="market", kind="money_flow_change", severity="high",
                                  title="外資 20 日累計由買轉賣",
                                  reason=f"{c20.iloc[-1 - lb] / 1e8:+,.0f} 億 → {c20.iloc[-1] / 1e8:+,.0f} 億",
                                  as_of=as_of))
        elif c20.iloc[-1 - lb] < 0 < c20.iloc[-1]:
            out.append(make_alert(category="market", kind="money_flow_change", severity="low",
                                  title="外資 20 日累計由賣轉買",
                                  reason=f"{c20.iloc[-1 - lb] / 1e8:+,.0f} 億 → {c20.iloc[-1] / 1e8:+,.0f} 億",
                                  as_of=as_of))
    tv = f.get("turnover")
    if tv is not None and len(tv.dropna()) >= 21:
        ratio = tv.iloc[-1] / tv.rolling(20).mean().iloc[-1]
        if ratio >= th["volume_spike_ratio"]:
            out.append(make_alert(category="market", kind="liquidity_spike", severity="medium",
                                  title="成交量暴增", reason=f"成交金額為 MA20 的 {ratio:.1f} 倍", as_of=as_of))
    vol = f.get("vol")
    if vol is not None and len(vol.dropna()) >= 60:
        s = vol.dropna().iloc[-250:]
        pct = (s < s.iloc[-1]).mean() * 100
        if pct >= th["volatility_spike_pct"]:
            out.append(make_alert(category="market", kind="volatility_spike", severity="high",
                                  title="波動度急升", reason=f"20 日實現波動度 {s.iloc[-1]:.1%}，位於 {pct:.0f} 百分位",
                                  as_of=as_of))
    return out


def detect_stock_alerts(sym: str, name: str, df: pd.DataFrame, index_close: pd.Series,
                        rs_now: float | None, rs_prev: float | None,
                        inst: pd.DataFrame | None, as_of: str) -> list[dict]:
    th = get_settings()["thresholds"]
    out: list[dict] = []
    label = f"{sym} {name}"
    c = df["close"]
    lb = th["breakout_lookback"]
    if len(c) > lb + 1:
        prev_high = c.iloc[-lb - 1:-1].max()
        prev_low = c.iloc[-lb - 1:-1].min()
        if c.iloc[-1] > prev_high:
            out.append(make_alert(category="stock", kind="breakout", severity="low", symbol=sym,
                                  title=f"{label} 突破 {lb} 日高點",
                                  reason=f"收盤 {c.iloc[-1]:,.2f} > 前高 {prev_high:,.2f}", as_of=as_of))
        elif c.iloc[-1] < prev_low:
            out.append(make_alert(category="stock", kind="breakdown", severity="high", symbol=sym,
                                  title=f"{label} 跌破 {lb} 日低點",
                                  reason=f"收盤 {c.iloc[-1]:,.2f} < 前低 {prev_low:,.2f}", as_of=as_of))
    v = df["volume"]
    if len(v) > 21 and v.rolling(20).mean().iloc[-1] > 0:
        ratio = v.iloc[-1] / v.rolling(20).mean().iloc[-1]
        if ratio >= th["volume_spike_ratio"]:
            out.append(make_alert(category="stock", kind="volume_spike", severity="medium", symbol=sym,
                                  title=f"{label} 爆量", reason=f"成交量為 MA20 的 {ratio:.1f} 倍", as_of=as_of))
    if rs_now is not None and rs_prev is not None:
        if rs_prev < th["rs_breakout"] <= rs_now:
            out.append(make_alert(category="stock", kind="rs_breakout", severity="low", symbol=sym,
                                  title=f"{label} 相對強度突破",
                                  reason=f"RS Score {rs_prev:.0f} → {rs_now:.0f}", as_of=as_of))
        elif rs_prev >= 50 > rs_now:
            out.append(make_alert(category="stock", kind="rs_reversal", severity="medium", symbol=sym,
                                  title=f"{label} 相對強度轉弱",
                                  reason=f"RS Score {rs_prev:.0f} → {rs_now:.0f}", as_of=as_of))
    w = th["divergence_window"]
    if price_up_other_down(index_close, c.reindex(index_close.index).ffill(), min_move=0.01):
        out.append(make_alert(category="stock", kind="relative_weakness", severity="medium", symbol=sym,
                              title=f"{label} 相對弱勢（大盤 ↑ 個股 ↓）",
                              reason=f"大盤 {w} 日 {_ret(index_close, w):+.1%}，個股 {_ret(c, w):+.1%}", as_of=as_of))
    if inst is not None and len(inst) >= 10:
        tot = inst[["foreign", "trust"]].sum(axis=1)
        days_buy = int((tot.iloc[-10:] > 0).sum())
        if days_buy >= 8:
            out.append(make_alert(category="stock", kind="institutional_accumulation", severity="low", symbol=sym,
                                  title=f"{label} 法人連續吸籌", reason=f"近 10 日有 {days_buy} 日外資+投信買超",
                                  as_of=as_of))
        elif days_buy <= 2:
            out.append(make_alert(category="stock", kind="institutional_distribution", severity="medium", symbol=sym,
                                  title=f"{label} 法人持續調節", reason=f"近 10 日有 {10 - days_buy} 日外資+投信賣超",
                                  as_of=as_of))
    return out


def detect_sector_alerts(sectors: list[dict], index_ret5: float | None, as_of: str) -> list[dict]:
    out: list[dict] = []
    if index_ret5 is None:
        return out
    for s in sectors:
        r5 = s["returns"].get("5")
        r20 = s["returns"].get("20")
        if r5 is None:
            continue
        if index_ret5 < 0 and r5 > 0.01:
            out.append(make_alert(category="sector", kind="sector_leadership", severity="low", symbol=s["name"],
                                  title=f"{s['name']} 逆勢領漲（潛在領導族群）",
                                  reason=f"類股 5 日 {r5:+.1%}，大盤 {index_ret5:+.1%}", as_of=as_of))
        elif r20 is not None and r20 > 0.03 and r5 < -0.03:
            out.append(make_alert(category="sector", kind="sector_rotation", severity="medium", symbol=s["name"],
                                  title=f"{s['name']} 資金流出（輪動）",
                                  reason=f"20 日 {r20:+.1%} 但 5 日 {r5:+.1%}", as_of=as_of))
        elif r5 - index_ret5 < -0.04:
            out.append(make_alert(category="sector", kind="sector_weakness", severity="medium", symbol=s["name"],
                                  title=f"{s['name']} 明顯弱於大盤",
                                  reason=f"類股 5 日 {r5:+.1%}，大盤 {index_ret5:+.1%}", as_of=as_of))
    return out
