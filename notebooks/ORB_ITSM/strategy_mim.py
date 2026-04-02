"""
strategy_mim.py
Market Intraday Momentum (MIM) for NQ futures.

Academic basis
--------------
Gao, Han, Li, Zhou (2018). "Market Intraday Momentum." JFE 129(2), 394-414.
Baltussen, Da, Lammers, Martens (2021). "Hedging Demand and Market Intraday
  Momentum." JFE 142(1), 377-403.

Key finding: The SAME-SESSION return from open to ~15:00 ET predicts the
return of the LAST 30 minutes (15:30-16:00). Driven by:
  - Gamma-hedging demand from option market makers (forced intraday rebalancing)
  - Leveraged ETF rebalancing (must buy/sell in direction of the day's return)
Both are STRUCTURAL, not pattern-mined, and persist across 45+ years and 60+
futures instruments.

Design (regime-invariant, single-parameter)
-------------------------------------------
  signal_bars : number of 5-min bars from session open to compute ROD signal
                e.g., signal_bars=36 => uses 9:30-12:30 (3-hour sub-session)

  r_rod = log(close[signal_bars-1] / open[0])   # rest-of-day return
  direction = sign(r_rod)                        # no threshold -- fully unconditional

  Entry: 15:30 ET (open of last 30-min bar)
  Exit:  15:45 ET (first exit opportunity) or EOD

CSCV grid (single dimension)
-----------------------------
  signal_bars : [18, 24, 36, 48]
    - 18 => 9:30-10:55 (1.5hr, "early session" confirmation)
    - 24 => 9:30-11:25 (2hr)
    - 36 => 9:30-12:25 (3hr, full morning session)
    - 48 => 9:30-13:25 (4hr, more of the day included)
  N = 4 variants -- minimal grid, single dimension
"""

import math
import numpy as np
import pandas as pd

INITIAL_EQUITY   = 50_000.0
MULTIPLIER       = 2
MAX_RISK_DOLLARS = 500

ATR_PERIOD     = 14
ATR_FALLBACK   = 200.0
SL_ATR_MULT    = 0.75   # backstop SL (rarely hit in 15-min window)

SIGNAL_BARS    = 36     # default: use 3-hour sub-session return as signal

ENTRY_HOUR     = 15
ENTRY_MINUTE   = 30
EXIT_HOUR      = 15
EXIT_MINUTE    = 45
FORCE_EXIT_H   = 15
FORCE_EXIT_M   = 55


def _compute_atr_lookup(df: pd.DataFrame, atr_period: int) -> dict:
    """Rolling daily-range ATR. Strictly no look-ahead."""
    day_ranges = {}
    for d, g in df.groupby(df.index.normalize()):
        day_ranges[d] = g['high'].max() - g['low'].min()
    all_dates  = sorted(day_ranges.keys())
    range_vals = [day_ranges[d] for d in all_dates]
    atr_lookup = {}
    for i, d in enumerate(all_dates):
        if i == 0:
            atr_lookup[d] = ATR_FALLBACK
        else:
            start  = max(0, i - atr_period)
            recent = range_vals[start:i]
            atr_lookup[d] = float(np.mean(recent)) if recent else ATR_FALLBACK
    return atr_lookup


def run_backtest(
    df: pd.DataFrame,
    signal_bars: int   = None,
    atr_period: int    = None,
    sl_atr_mult: float = None,
) -> tuple:
    """
    Market Intraday Momentum backtest.

    Parameters
    ----------
    df          : 5-min OHLCV, timezone-aware ET index
    signal_bars : bars from open used to compute ROD signal (default 36 = 3hr)
    atr_period  : rolling ATR lookback in days (default 14)
    sl_atr_mult : backstop SL distance in ATR multiples (default 0.75)
    """
    sig_b    = signal_bars  if signal_bars  is not None else SIGNAL_BARS
    atr_p    = atr_period   if atr_period   is not None else ATR_PERIOD
    sl_mult  = sl_atr_mult  if sl_atr_mult  is not None else SL_ATR_MULT

    equity    = INITIAL_EQUITY
    trade_log = []

    atr_lookup = _compute_atr_lookup(df, atr_p)
    day_groups = {d: g for d, g in df.groupby(df.index.normalize())}
    dates      = sorted(day_groups.keys())

    for date in dates:
        day_df = day_groups[date]
        bars   = list(day_df.itertuples())

        if len(bars) < sig_b + 1:
            continue

        # --- MIM signal: return of first sig_b bars (no threshold) ---
        open_px    = bars[0].open
        signal_cls = bars[sig_b - 1].close
        if open_px <= 0 or signal_cls <= 0:
            continue
        r_rod     = math.log(signal_cls / open_px)
        direction = 1 if r_rod > 0 else -1

        # --- Find entry bar (15:30) ---
        entry_bar = None
        for bar in bars:
            if bar.Index.hour == ENTRY_HOUR and bar.Index.minute == ENTRY_MINUTE:
                entry_bar = bar
                break
        if entry_bar is None:
            continue

        entry_px   = entry_bar.open
        entry_time = entry_bar.Index
        atr_val    = atr_lookup.get(date, ATR_FALLBACK)
        sl_dist    = sl_mult * atr_val
        contracts  = max(1, math.floor(MAX_RISK_DOLLARS / (sl_dist * MULTIPLIER)))
        sl_px      = entry_px - direction * sl_dist

        # --- Exit: 15:45 or EOD, with backstop SL ---
        exit_px = exit_time = exit_reason = None
        in_trade = False
        for bar in bars:
            if bar.Index < entry_time:
                continue
            if not in_trade:
                in_trade = True
                continue   # skip entry bar itself

            bar_time   = bar.Index
            time_exit  = (bar_time.hour > EXIT_HOUR or
                          (bar_time.hour == EXIT_HOUR and bar_time.minute >= EXIT_MINUTE))
            force_exit = (bar_time.hour > FORCE_EXIT_H or
                          (bar_time.hour == FORCE_EXIT_H and bar_time.minute >= FORCE_EXIT_M))
            hit_sl     = ((direction == 1  and bar.low  <= sl_px) or
                          (direction == -1 and bar.high >= sl_px))

            if hit_sl:
                exit_px, exit_reason = sl_px, "SL"
            elif time_exit or force_exit:
                exit_px, exit_reason = bar.close, "TIME"
            else:
                continue
            exit_time = bar_time
            break

        if exit_px is None:
            exit_px, exit_time, exit_reason = bars[-1].close, bars[-1].Index, "EOD"

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
            "sl_pts":       round(sl_dist, 1),
            "r_rod":        round(r_rod, 5),
            "signal_bars":  sig_b,
            "pnl":          round(pnl, 2),
            "equity_after": round(equity, 2),
        })

    cols = [
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "atr", "sl_pts",
        "r_rod", "signal_bars", "pnl", "equity_after",
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
