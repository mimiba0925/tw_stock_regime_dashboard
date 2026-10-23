"""
將後端完整計算結果（大盤 Summary / Trend / Breadth / Flow / Liquidity / Risk / Sectors / Watchlist / 每檔自選股 Detail / Alerts）
匯出為靜態 snapshot.js，並將前端 Vite 打包產物複製至專案根目錄，讓 GitHub Pages 可直接作為無後端靜態網站瀏覽。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

sys.path.insert(0, str(BACKEND))

from app import main as M  # noqa: E402
from app.config import load_watchlist  # noqa: E402
from app.service import SERVICE  # noqa: E402


def build_snapshot() -> dict:
    print("▶ [1/3] 計算台股大盤與自選個股最新狀態快照 ...")
    SERVICE.get(force=False)
    snap: dict[str, object] = {
        "/api/market/summary": M.market_summary(),
        "/api/market/trend": M.market_trend(),
        "/api/market/breadth": M.market_breadth(),
        "/api/market/flow": M.market_flow(),
        "/api/market/liquidity": M.market_liquidity(),
        "/api/market/risk": M.market_risk(),
        "/api/sectors": M.sectors(),
        "/api/stocks/watchlist": M.watchlist(),
        "/api/alerts": M.alerts(),
        "/api/config/ui": M.ui_config(),
    }
    for r in load_watchlist():
        sym = r["symbol"]
        try:
            snap[f"/api/stocks/{sym}"] = M.stock(sym)
            snap[f"/api/stocks/{sym}/trend"] = M.stock_trend(sym)
            snap[f"/api/stocks/{sym}/flow"] = M.stock_flow(sym)
            snap[f"/api/stocks/{sym}/fundamentals"] = M.stock_fund(sym)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ 略過 {sym}: {e}")
    return snap


def build_frontend() -> None:
    print("▶ [2/3] 執行前端 Vite 生產環境打包 (npm run build) ...")
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True)


def export_to_root(snap: dict) -> None:
    print("▶ [3/3] 輸出靜態網站檔案至根目錄（供 GitHub Pages 直接部署）...")
    dist = FRONTEND / "dist"
    shutil.copy2(dist / "index.html", ROOT / "index.html")
    assets_dst = ROOT / "assets"
    if assets_dst.exists():
        shutil.rmtree(assets_dst)
    shutil.copytree(dist / "assets", assets_dst)

    payload = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    (ROOT / "snapshot.js").write_text(f"window.__DASHBOARD_SNAPSHOT__={payload};\n", encoding="utf-8")
    print(f"✔ 已產生 index.html、assets/、snapshot.js ({len(payload) / 1024:.1f} KB)")


if __name__ == "__main__":
    s = build_snapshot()
    build_frontend()
    export_to_root(s)
