"""
main.py
Entry point for the NQ Futures ORB Strategy Backtest.

Usage
-----
  python main.py               # use cached data if available
  python main.py --refresh     # force re-download from Yahoo Finance
"""

import sys
import os

from data_fetch import fetch_data
from strategy   import run_backtest
from analysis   import print_summary, plot_all


def main():
    refresh = "--refresh" in sys.argv or "-r" in sys.argv

    # ── 1. Fetch data ───────────────────────────────────────────────────────
    df = fetch_data(refresh=refresh)

    if df.empty:
        print("[main] ERROR: No data returned. Exiting.")
        sys.exit(1)

    print(f"[main] Data loaded: {len(df):,} 5-min bars  "
          f"({df.index[0].strftime('%Y-%m-%d')} -> "
          f"{df.index[-1].strftime('%Y-%m-%d')})")

    # ── 2. Run backtest ─────────────────────────────────────────────────────
    print("[main] Running backtest ...")
    trades, equity = run_backtest(df)

    if trades.empty:
        print("[main] WARNING: Backtest produced zero trades.\n"
              "       The signal conditions may be too restrictive for the\n"
              "       available 60-day data window. Try --refresh to pull\n"
              "       fresh data or loosen strategy parameters.")
        sys.exit(0)

    print(f"[main] Backtest complete — {len(trades)} trades over "
          f"{trades['date'].nunique()} trading days.")

    # ── 3. Print performance summary ────────────────────────────────────────
    metrics = print_summary(trades, equity)

    # ── 4. Save charts ──────────────────────────────────────────────────────
    print("[main] Generating charts ...")
    plot_all(trades, equity)

    # ── 5. Save trade log ───────────────────────────────────────────────────
    os.makedirs("output", exist_ok=True)
    trade_log_path = os.path.join("output", "trade_log.csv")
    trades.to_csv(trade_log_path, index=False)
    print(f"[main] Trade log saved -> {trade_log_path}")

    print("\n[main] Done. Review ./output/ for charts and trade_log.csv.")


if __name__ == "__main__":
    main()
