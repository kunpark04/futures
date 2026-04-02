"""
strategy_pitsm.py
Pure Intraday Time-Series Momentum (PITSM) strategy for NQ futures.

Academic basis
--------------
- ITSM: first-30-min return predicts rest-of-day direction in equity index futures
  (Gao et al., Notre Dame; Huss & Malitius, Birmingham; AQR gamma-hedging study)
- Time-based exit at 15:30 matches ITSM literature specification exactly
- ATR-based stop is regime-adaptive (avoids fixed-stop regime overfitting)

Design rationale (informed by CSCV analysis of ORB v4/v5)
----------------------------------------------------------
- NO fixed SL/TP: the #1 PBO driver in ORB strategies (70-84pp CSCV spread)
- NO EMA / RSI filters: 0pp CSCV spread -- irrelevant to overfitting
- NO opening-range breakout: replaced by directional ITSM signal
- ATR stop adapts to volatility: robust across calm and volatile regimes
- Time exit at 15:30: academically specified, no TP parameter to overfit

Parameters
----------
ITSM_BARS       : int   bars in opening window (3=15min, 4=20min, 5=25min, 6=30min)
ITSM_THRESHOLD  : float min |r_open| to trade (0.0 = always trade; 0.001 = 0.1% min)
ATR_PERIOD      : int   rolling lookback for daily-range ATR
ATR_STOP_MULT   : float stop distance as multiple of ATR (e.g. 2.0 = 2x daily range)
EXIT_HOUR/MIN   : int   forced exit time (default 15:30 matching ITSM literature)
"""

import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration (defaults -- override via run_backtest() kwargs)
# ---------------------------------------------------------------------------
INITIAL_EQUITY  = 50_000.0
MULTIPLIER      = 2           # MNQ: $2 per index point
MAX_RISK_DOLLARS = 500        # target max loss per trade at stop

ITSM_BARS      = 6            # 6 x 5-min = 30-min opening window (9:30-10:00)
ITSM_THRESHOLD = 0.0          # min |r_open| to trade (log return, e.g. 0.001 = 0.1%)
ATR_PERIOD     = 14           # rolling daily-range ATR lookback (days)
ATR_STOP_MULT  = 2.0          # stop = ATR_STOP_MULT * ATR from entry
ATR_FALLBACK   = 200.0        # fallback ATR when insufficient history (NQ ~200pt avg range)

EXIT_HOUR      = 15
EXIT_MINUTE    = 30           # force-close at 15:30 (matches ITSM literature)
FORCE_EXIT_H   = 15
FORCE_EXIT_M   = 45           # hard backstop: close any leftover position at 15:45


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _compute_atr_lookup(df: pd.DataFrame, atr_period: int) -> dict:
    """
    Build a {date -> ATR} lookup using rolling daily session range.

    Session range = max(high) - min(low) across all 5-min RTH bars for that day.
    ATR for day d = mean of the previous atr_period days' session ranges.
    No look-ahead: today's bars are NOT included in today's ATR.

    Returns
    -------
    dict mapping pd.Timestamp (normalized, midnight) -> float ATR in NQ points
    """
    day_ranges = {}
    for d, g in df.groupby(df.index.normalize()):
        day_ranges[d] = g['high'].max() - g['low'].min()

    all_dates   = sorted(day_ranges.keys())
    range_vals  = [day_ranges[d] for d in all_dates]
    atr_lookup  = {}

    for i, d in enumerate(all_dates):
        if i == 0:
            atr_lookup[d] = ATR_FALLBACK
        else:
            start  = max(0, i - atr_period)
            recent = range_vals[start:i]          # excludes today (strict no look-ahead)
            atr_lookup[d] = float(np.mean(recent)) if recent else ATR_FALLBACK

    return atr_lookup


def _itsm_signal(day_df: pd.DataFrame, itsm_bars: int, threshold: float):
    """
    Compute the ITSM direction from the first itsm_bars bars.

    r_open = log(close[itsm_bars-1] / open[0])

    Returns
    -------
    direction : int  +1 long, -1 short, 0 no trade (|r_open| < threshold)
    r_open    : float the raw log return (for logging)
    """
    if len(day_df) < itsm_bars + 1:
        return 0, 0.0

    open_px  = day_df.iloc[0]['open']
    close_px = day_df.iloc[itsm_bars - 1]['close']   # last bar of opening window

    if open_px <= 0:
        return 0, 0.0

    r_open = math.log(close_px / open_px)

    if abs(r_open) < threshold:
        return 0, r_open

    return (1 if r_open > 0 else -1), r_open


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def _calc_contracts(atr_val: float, atr_stop_mult: float) -> int:
    """
    Scale contracts so that ATR-stop loss ~ MAX_RISK_DOLLARS.

    contracts = floor(MAX_RISK / (atr_stop_mult * atr_val * MULTIPLIER))
    Minimum 1 contract.
    """
    stop_pts = atr_stop_mult * atr_val
    if stop_pts <= 0:
        return 1
    return max(1, math.floor(MAX_RISK_DOLLARS / (stop_pts * MULTIPLIER)))


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    itsm_bars: int = None,
    itsm_threshold: float = None,
    atr_period: int = None,
    atr_stop_mult: float = None,
) -> tuple:
    """
    Run Pure ITSM backtest over all days in df.

    Parameters
    ----------
    df             : 5-min OHLCV, timezone-aware ET index
    itsm_bars      : number of opening bars for signal window (default 6 = 30 min)
    itsm_threshold : min |r_open| log return to trade (default 0.0)
    atr_period     : rolling ATR lookback in days (default 14)
    atr_stop_mult  : stop = this multiple of daily ATR (default 2.0)

    Returns
    -------
    trades       : pd.DataFrame  one row per trade
    equity_curve : pd.Series     daily equity snapshots
    """
    itsm_b   = itsm_bars      if itsm_bars      is not None else ITSM_BARS
    itsm_thr = itsm_threshold if itsm_threshold is not None else ITSM_THRESHOLD
    atr_p    = atr_period     if atr_period     is not None else ATR_PERIOD
    atr_mult = atr_stop_mult  if atr_stop_mult  is not None else ATR_STOP_MULT

    equity    = INITIAL_EQUITY
    trade_log = []

    # Pre-compute ATR lookup (rolling daily range, no look-ahead)
    atr_lookup = _compute_atr_lookup(df, atr_p)

    # Pre-compute day groups (O(T) scan once instead of per-day)
    day_groups = {d: g for d, g in df.groupby(df.index.normalize())}
    dates      = sorted(day_groups.keys())

    for date in dates:
        day_df = day_groups[date]

        # Need at least itsm_b bars for signal + 1 entry bar + bars to hold
        if len(day_df) < itsm_b + 2:
            continue

        # --- Compute ITSM signal (no look-ahead: uses bars 0..itsm_b-1 only) ---
        direction, r_open = _itsm_signal(day_df, itsm_b, itsm_thr)
        if direction == 0:
            continue

        # --- Entry: open of bar[itsm_b] (first bar after signal window) ---
        bars      = list(day_df.itertuples())
        entry_bar = bars[itsm_b]
        entry_px  = entry_bar.open
        entry_time = entry_bar.Index

        atr_val   = atr_lookup.get(date, ATR_FALLBACK)
        stop_dist = atr_mult * atr_val
        sl_px     = entry_px - direction * stop_dist
        contracts = _calc_contracts(atr_val, atr_mult)

        # --- Scan bars from entry onward for stop or time exit ---
        in_trade    = True
        exit_px     = None
        exit_time   = None
        exit_reason = None

        for bar in bars[itsm_b:]:
            if not in_trade:
                break

            bar_time = bar.Index

            # Primary time exit at EXIT_HOUR:EXIT_MINUTE
            time_exit = (
                bar_time.hour > EXIT_HOUR
                or (bar_time.hour == EXIT_HOUR and bar_time.minute >= EXIT_MINUTE)
            )
            # Hard backstop
            force_exit = (
                bar_time.hour > FORCE_EXIT_H
                or (bar_time.hour == FORCE_EXIT_H and bar_time.minute >= FORCE_EXIT_M)
            )

            hit_sl = (
                (direction == 1  and bar.low  <= sl_px) or
                (direction == -1 and bar.high >= sl_px)
            )

            if hit_sl:
                exit_px     = sl_px
                exit_reason = "SL"
            elif time_exit or force_exit:
                exit_px     = bar.close
                exit_reason = "TIME"
            else:
                continue

            exit_time = bar_time
            in_trade  = False

        if exit_px is None:
            # Closed without hitting any exit (shouldn't happen, but guard)
            exit_px     = bars[-1].close
            exit_time   = bars[-1].Index
            exit_reason = "EOD"

        points = (exit_px - entry_px) * direction
        pnl    = points * MULTIPLIER * contracts
        equity += pnl

        trade_log.append({
            "date":         date.date(),
            "direction":    "LONG" if direction == 1 else "SHORT",
            "entry_time":   entry_time,
            "exit_time":    exit_time,
            "exit_reason":  exit_reason,
            "entry_price":  round(entry_px, 2),
            "exit_price":   round(exit_px, 2),
            "contracts":    contracts,
            "atr":          round(atr_val, 1),
            "r_open":       round(r_open, 5),
            "pnl":          round(pnl, 2),
            "equity_after": round(equity, 2),
        })

    cols = [
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "atr", "r_open",
        "pnl", "equity_after",
    ]
    trades = pd.DataFrame(trade_log) if trade_log else pd.DataFrame(columns=cols)

    if not trades.empty:
        eq = trades.set_index("date")["equity_after"]
        eq.index = pd.to_datetime(eq.index)
        all_dates    = pd.date_range(eq.index.min(), eq.index.max(), freq="B")
        equity_curve = eq.reindex(all_dates).ffill().fillna(INITIAL_EQUITY)
        equity_curve.name = "equity"
    else:
        equity_curve = pd.Series(
            [INITIAL_EQUITY],
            index=pd.to_datetime([pd.Timestamp.today().normalize()]),
            name="equity",
        )

    return trades, equity_curve
