"""集中設定載入。所有模組皆透過 get_settings() / load_watchlist() 取得設定。"""
from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"


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


def load_watchlist() -> list[dict[str, str]]:
    """自選股名單：每次呼叫重新讀取 CSV，修改後無需重啟。"""
    return _load_csv(resolve(get_settings()["data_source"]["watchlist_csv"]))


def load_universe() -> list[dict[str, str]]:
    """類股 / 廣度樣本股票池。"""
    return _load_csv(resolve(get_settings()["data_source"]["universe_csv"]))


def save_watchlist(rows: list[dict[str, str]]) -> None:
    path = resolve(get_settings()["data_source"]["watchlist_csv"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "name", "market", "sector"])
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in ["symbol", "name", "market", "sector"]})


def yahoo_symbol(symbol: str, market: str) -> str:
    return f"{symbol}.TWO" if market in ("TPEX", "OTC") else f"{symbol}.TW"
