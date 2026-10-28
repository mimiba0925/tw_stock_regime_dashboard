"""
建置最新台股大盤 + 自選個股 Market Regime Dashboard 靜態快照 (snapshot.js) 並自動同步至 GitHub Pages
參考 sentiment_liquidity_dashboard / 00981a_tracker 的 SSH 免密碼推送架構 (git@github.com:mimiba0925/...)
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / "backend" / ".venv" / "bin" / "python"


def run_cmd(cmd, check=True, capture=False):
    return subprocess.run(cmd, cwd=ROOT, check=check, capture_output=capture, text=True)


def main():
    py = str(VENV_PY) if VENV_PY.exists() else sys.executable
    print("=" * 65)
    print(" [Step 0/2] 先同步 GitHub 遠端最新變更 (git pull --rebase) ...")
    print("=" * 65)
    run_cmd(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=False)

    print("\n" + "=" * 65)
    print(" [Step 1/2] 執行 build_static.py --force 產生最新靜態網站與 snapshot.js ...")
    print("=" * 65)
    run_cmd([py, "build_static.py", "--force"], check=True)

    print("\n" + "=" * 65)
    print(" [Step 2/2] 準備同步最新儀表板至 GitHub ...")
    print("=" * 65)

    rem = run_cmd(["git", "remote", "-v"], check=False, capture=True)
    if "origin" not in (rem.stdout or ""):
        print("⚠️ 尚未綁定 GitHub 遠端倉庫 (remote origin)。")
        print("請先在 GitHub 建立一個 Public 專案（例如 tw_stock_regime_dashboard），然後執行：")
        print(f'  cd "{ROOT}"')
        print("  git remote add origin git@github.com:mimiba0925/tw_stock_regime_dashboard.git")
        print("  git push -u origin main")
        return 0

    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    run_cmd(["git", "add", "-A"], check=True)

    commit_res = run_cmd(
        ["git", "commit", "-m", f"Auto update TW market regime dashboard: {today_str}"],
        check=False,
        capture=True,
    )
    combined = (commit_res.stdout or "") + (commit_res.stderr or "")
    if "nothing to commit" in combined:
        print("ℹ️ 資料無新變動，略過 commit。")
    else:
        print("✔ git commit 完成")

    run_cmd(["git", "push", "-u", "origin", "main"], check=True)
    print("✅ 成功同步最新台股 Market Regime Dashboard 至 GitHub！")
    return 0


if __name__ == "__main__":
    sys.exit(main())
