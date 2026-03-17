"""
analysis.py
Performance metrics and chart generation for the NQ ORB strategy backtest.
Uses only numpy, pandas, matplotlib, and seaborn.
"""

import os
import math
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — safe for all environments
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns

OUTPUT_DIR = "output"

# ---------------------------------------------------------------------------
# Metric helpers (pure numpy / pandas, no scipy)
# ---------------------------------------------------------------------------

def _sharpe(pnl_series: pd.Series, trades_per_year: float = 252.0) -> float:
    """
    Per-trade Sharpe ratio annualised by the expected number of trades/year.
    Uses 0 as risk-free rate (common for futures strategies).
    """
    if len(pnl_series) < 2:
        return float("nan")
    mean = pnl_series.mean()
    std  = pnl_series.std(ddof=1)
    if std == 0:
        return float("nan")
    return (mean / std) * math.sqrt(trades_per_year)


def _max_drawdown(equity: pd.Series) -> tuple:
    """
    Return (max_drawdown_pct, peak_date, trough_date).
    max_drawdown_pct is expressed as a positive percentage (e.g. 12.5 = 12.5%).
    """
    running_peak = equity.cummax()
    drawdown     = (equity - running_peak) / running_peak * 100.0
    worst_idx    = drawdown.idxmin()
    worst_dd     = drawdown.min()

    # Find the peak that preceded the worst trough
    peak_idx = running_peak.loc[:worst_idx].idxmax()
    return abs(worst_dd), peak_idx, worst_idx


def _profit_factor(pnl: pd.Series) -> float:
    gross_wins   = pnl[pnl > 0].sum()
    gross_losses = abs(pnl[pnl < 0].sum())
    if gross_losses == 0:
        return float("inf")
    return gross_wins / gross_losses


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_summary(trades: pd.DataFrame, equity: pd.Series) -> dict:
    """
    Print a formatted performance summary table and return metrics as a dict.
    """
    if trades.empty:
        print("\n[analysis] No trades were generated. "
              "Check strategy parameters or data range.")
        return {}

    total    = len(trades)
    wins     = (trades["pnl"] > 0).sum()
    losses   = (trades["pnl"] < 0).sum()
    breakevs = (trades["pnl"] == 0).sum()
    win_rate = wins / total * 100.0

    # Average bars/day → trades per year proxy
    days_traded    = trades["date"].nunique()
    total_days_est = max(days_traded, 1)
    # Assume ~252 trading days/yr, scale by how many days we actually traded
    # to get a reasonable annualisation factor
    trades_per_year = (total / total_days_est) * 252.0

    sharpe    = _sharpe(trades["pnl"], trades_per_year)
    max_dd, pk_date, tr_date = _max_drawdown(equity)
    pf        = _profit_factor(trades["pnl"])
    net_pnl   = trades["pnl"].sum()
    final_eq  = equity.iloc[-1]
    total_ret = (final_eq - 50_000.0) / 50_000.0 * 100.0
    avg_win   = trades.loc[trades["pnl"] > 0, "pnl"].mean() if wins  else 0.0
    avg_loss  = trades.loc[trades["pnl"] < 0, "pnl"].mean() if losses else 0.0

    sep = "-" * 50
    print(f"\n{'=' * 50}")
    print(f"  NQ ORB STRATEGY -- BACKTEST RESULTS")
    print(f"{'=' * 50}")
    print(f"  {'Total Trades':<28} {total:>10}")
    print(f"  {'Winning Trades':<28} {wins:>10}")
    print(f"  {'Losing Trades':<28} {losses:>10}")
    print(f"  {'Break-even Trades':<28} {breakevs:>10}")
    print(sep)
    print(f"  {'Win Rate':<28} {win_rate:>9.1f}%")
    print(f"  {'Sharpe Ratio':<28} {sharpe:>10.2f}")
    print(f"  {'Profit Factor':<28} {pf:>10.2f}")
    print(sep)
    print(f"  {'Net P&L':<28} ${net_pnl:>+10,.2f}")
    print(f"  {'Total Return':<28} {total_ret:>+9.1f}%")
    print(f"  {'Final Equity':<28} ${final_eq:>10,.2f}")
    print(f"  {'Max Drawdown':<28} {max_dd:>9.1f}%")
    print(sep)
    print(f"  {'Avg Winning Trade':<28} ${avg_win:>+10,.2f}")
    print(f"  {'Avg Losing Trade':<28} ${avg_loss:>+10,.2f}")
    print(f"  {'Days Traded':<28} {days_traded:>10}")
    print(f"{'=' * 50}\n")

    # Warn if targets not met
    if win_rate < 50.0:
        print(f"  [!] Win rate {win_rate:.1f}% is below the 50% target.")
    if sharpe < 1.0:
        print(f"  [!] Sharpe {sharpe:.2f} is below the 1.0 target.")

    return {
        "total_trades": total,
        "win_rate_pct": round(win_rate, 2),
        "sharpe": round(sharpe, 3),
        "profit_factor": round(pf, 3),
        "net_pnl": round(net_pnl, 2),
        "total_return_pct": round(total_ret, 2),
        "final_equity": round(final_eq, 2),
        "max_drawdown_pct": round(max_dd, 2),
    }


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _save(fig, name: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[analysis] Saved chart -> {path}")


def _plot_equity_curve(equity: pd.Series):
    """Equity curve with drawdown shading."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7),
                                   gridspec_kw={"height_ratios": [3, 1]},
                                   sharex=True)
    fig.patch.set_facecolor("#0d1117")
    for ax in (ax1, ax2):
        ax.set_facecolor("#0d1117")
        ax.tick_params(colors="white")
        ax.spines[:].set_color("#444")
        ax.yaxis.label.set_color("white")
        ax.xaxis.label.set_color("white")
        ax.title.set_color("white")

    # Equity
    ax1.plot(equity.index, equity.values, color="#00d4aa", linewidth=1.5,
             label="Equity")
    ax1.axhline(50_000, color="#555", linewidth=0.8, linestyle="--",
                label="Initial Capital")
    ax1.fill_between(equity.index, 50_000, equity.values,
                     where=equity.values >= 50_000,
                     color="#00d4aa", alpha=0.08)
    ax1.fill_between(equity.index, 50_000, equity.values,
                     where=equity.values < 50_000,
                     color="#ff4444", alpha=0.15)
    ax1.set_title("NQ ORB Strategy — Equity Curve", fontsize=13, pad=10)
    ax1.set_ylabel("Equity ($)", fontsize=10)
    ax1.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white")
    ax1.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: f"${x:,.0f}"))

    # Drawdown
    running_peak = equity.cummax()
    drawdown = (equity - running_peak) / running_peak * 100.0
    ax2.fill_between(equity.index, drawdown.values, 0,
                     color="#ff4444", alpha=0.6, label="Drawdown")
    ax2.set_ylabel("Drawdown (%)", fontsize=9)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=30, ha="right")

    plt.tight_layout(pad=1.5)
    _save(fig, "01_equity_curve.png")


def _plot_monthly_heatmap(trades: pd.DataFrame):
    """Monthly P&L heatmap (seaborn)."""
    if trades.empty:
        return

    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    t["year"]  = t["date"].dt.year
    t["month"] = t["date"].dt.month

    monthly = t.groupby(["year", "month"])["pnl"].sum().reset_index()
    pivot   = monthly.pivot(index="year", columns="month", values="pnl")
    pivot.columns = [
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec"
    ][:len(pivot.columns)]

    fig, ax = plt.subplots(figsize=(max(8, len(pivot.columns) * 1.1),
                                    max(3, len(pivot) * 0.9)))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")

    sns.heatmap(
        pivot,
        annot=True,
        fmt=".0f",
        cmap=sns.diverging_palette(10, 130, as_cmap=True),
        center=0,
        linewidths=0.5,
        linecolor="#222",
        ax=ax,
        annot_kws={"size": 9},
    )
    ax.set_title("Monthly P&L ($) Heatmap", color="white", fontsize=12, pad=8)
    ax.tick_params(colors="white", labelsize=9)
    ax.set_xlabel("Month", color="white", fontsize=9)
    ax.set_ylabel("Year",  color="white", fontsize=9)
    ax.collections[0].colorbar.ax.tick_params(colors="white")

    plt.tight_layout()
    _save(fig, "02_monthly_heatmap.png")


def _plot_pnl_distribution(trades: pd.DataFrame):
    """Trade P&L histogram + KDE (seaborn)."""
    if trades.empty:
        return

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    ax.spines[:].set_color("#444")

    pnl = trades["pnl"]
    sns.histplot(pnl, bins=25, kde=True, ax=ax,
                 color="#00d4aa", edgecolor="#0d1117", alpha=0.7,
                 line_kws={"linewidth": 2})
    ax.axvline(0, color="#ff4444", linewidth=1.2, linestyle="--", label="Break-even")
    ax.axvline(pnl.mean(), color="#ffd700", linewidth=1.2,
               linestyle="--", label=f"Mean ${pnl.mean():,.0f}")
    ax.set_title("Trade P&L Distribution", color="white", fontsize=12)
    ax.set_xlabel("P&L per Trade ($)", color="white")
    ax.set_ylabel("Count", color="white")
    ax.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white")

    plt.tight_layout()
    _save(fig, "03_pnl_distribution.png")


def _plot_drawdown(equity: pd.Series):
    """Standalone drawdown chart."""
    running_peak = equity.cummax()
    drawdown     = (equity - running_peak) / running_peak * 100.0

    fig, ax = plt.subplots(figsize=(12, 4))
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#0d1117")
    ax.tick_params(colors="white")
    ax.spines[:].set_color("#444")

    ax.fill_between(equity.index, drawdown.values, 0,
                    color="#ff4444", alpha=0.55, label="Drawdown")
    ax.plot(equity.index, drawdown.values, color="#ff6666", linewidth=0.8)
    ax.set_title("Strategy Drawdown Over Time", color="white", fontsize=12)
    ax.set_xlabel("Date", color="white")
    ax.set_ylabel("Drawdown (%)", color="white")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend(fontsize=9, facecolor="#1a1a2e", labelcolor="white")

    plt.tight_layout()
    _save(fig, "04_drawdown.png")


def plot_all(trades: pd.DataFrame, equity: pd.Series):
    """Generate and save all four charts."""
    _plot_equity_curve(equity)
    _plot_monthly_heatmap(trades)
    _plot_pnl_distribution(trades)
    _plot_drawdown(equity)
    print(f"[analysis] All charts saved to ./{OUTPUT_DIR}/")
