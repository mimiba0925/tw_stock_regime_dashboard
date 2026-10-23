"""集中設定載入。所有模組皆透過 get_settings() / load_watchlist() 取得設定。"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ).replace(tzinfo=None)


def today_taipei():
    return now_taipei().date()


@lru_cache(maxsize=1)
def get_settings() -> dict[str, Any]:
    with open(CONFIG_DIR / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    rows: list[dict[str, str]] = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            sym = (r.get("symbol") or "").strip()
            if not sym or sym.startswith("#"):
                continue
            rows.append({
                "symbol": sym,
                "name": (r.get("name") or sym).strip(),
                "market": (r.get("market") or "TWSE").strip().upper(),
                "sector": (r.get("sector") or "未分類").strip(),
            })
    return rows


def _sym_sort_key(row: dict[str, str]):
    s = (row.get("symbol") or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return (int(digits) if digits else 999999, s)


def load_watchlist() -> list[dict[str, str]]:
    """自選股名單：每次呼叫重新讀取 CSV，並依股票代號由小到大排序。"""
    rows = _load_csv(resolve(get_settings()["data_source"]["watchlist_csv"]))
    rows.sort(key=_sym_sort_key)
    return rows


def load_universe() -> list[dict[str, str]]:
    """類股 / 廣度樣本股票池。"""
    return _load_csv(resolve(get_settings()["data_source"]["universe_csv"]))


def save_watchlist(rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=_sym_sort_key)
    path = resolve(get_settings()["data_source"]["watchlist_csv"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "name", "market", "sector"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in ["symbol", "name", "market", "sector"]})


def yahoo_symbol(symbol: str, market: str) -> str:
    return f"{symbol}.TWO" if market in ("TPEX", "OTC") else f"{symbol}.TW"
