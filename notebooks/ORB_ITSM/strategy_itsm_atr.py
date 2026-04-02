"""
strategy_itsm_atr.py
ITSM with ATR-Scaled Risk Management (ITSM-ATR) for NQ futures.

Academic basis
--------------
- ITSM direction: first-30-min return predicts rest-of-day direction in equity
  index futures (Notre Dame / Birmingham / AQR gamma-hedging study)
- ATR-scaled stops: regime-adaptive risk management; proportional to current
  volatility so risk stays constant across calm and volatile regimes

Key design (informed by CSCV v4/v5 analysis)
---------------------------------------------
- NO fixed SL/TP in points: primary PBO driver in ORB (70-84pp spread)
  -> Replaced by SL = sl_atr_mult x ATR and TP = tp_atr_mult x ATR
  -> When ATR doubles, both stops double: same proportional risk every day
  -> Expected CSCV spread: near-zero (regime-agnostic by construction)
- NO EMA / RSI: zero CSCV contribution, pure noise in parameter grid
- NO OR breakout: replaced by ITSM directional signal
- Time exit at 15:30: backstop exit if neither SL nor TP fires

Signal
------
  r_open = log(close[itsm_bars-1] / open[0])       # first itsm_bars x 5-min
  direction = +1 if r_open > itsm_threshold else
              -1 if r_open < -itsm_threshold else
               0 (no trade)

Risk (ATR-scaled, 2:1 RR default)
----------------------------------
  SL = sl_atr_mult x ATR   (default 0.75 x ATR ~ 150 pts at ATR=200)
  TP = tp_atr_mult x ATR   (default 1.5  x ATR ~ 300 pts at ATR=200)
  contracts = floor(MAX_RISK / (SL x MULTIPLIER)), min 1
"""

import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INITIAL_EQUITY   = 50_000.0
MULTIPLIER       = 2          # MNQ: $2 per NQ index point
MAX_RISK_DOLLARS = 500        # target max dollar loss when SL fires

ITSM_BARS      = 6            # 6 x 5-min = 30-min opening window (9:30-10:00)
ITSM_THRESHOLD = 0.001        # min |r_open| to trade (log return; 0.001 ~ 0.1%)
ATR_PERIOD     = 14           # rolling daily-range ATR lookback in days
ATR_FALLBACK   = 200.0        # fallback ATR for cold-start days

SL_ATR_MULT    = 0.75         # stop loss   = SL_ATR_MULT  x ATR
TP_ATR_MULT    = 1.50         # take profit = TP_ATR_MULT  x ATR  (2:1 RR)

EXIT_HOUR      = 15
EXIT_MINUTE    = 30           # time-based backstop at 15:30
FORCE_EXIT_H   = 15
FORCE_EXIT_M   = 45           # hard close at 15:45


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_atr_lookup(df: pd.DataFrame, atr_period: int) -> dict:
    """
    Rolling daily-range ATR lookup {date -> ATR}.
    ATR at day d = mean of the previous atr_period days' (max_high - min_low).
    Strictly no look-ahead: today's range is excluded.
    """
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


# ---------------------------------------------------------------------------
# Core backtest
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    itsm_bars: int       = None,
    itsm_threshold: float = None,
    atr_period: int      = None,
    sl_atr_mult: float   = None,
    tp_atr_mult: float   = None,
) -> tuple:
    """
    Run ITSM-ATR backtest over all days in df.

    Parameters
    ----------
    df             : 5-min OHLCV, timezone-aware ET index
    itsm_bars      : opening-window bars for ITSM signal (default 6 = 30 min)
    itsm_threshold : min |r_open| log return to trade (default 0.001)
    atr_period     : rolling ATR lookback in days (default 14)
    sl_atr_mult    : SL distance in ATR multiples (default 0.75)
    tp_atr_mult    : TP distance in ATR multiples (default 1.50)

    Returns
    -------
    trades       : pd.DataFrame
    equity_curve : pd.Series
    """
    itsm_b   = itsm_bars      if itsm_bars      is not None else ITSM_BARS
    itsm_thr = itsm_threshold if itsm_threshold is not None else ITSM_THRESHOLD
    atr_p    = atr_period     if atr_period     is not None else ATR_PERIOD
    sl_mult  = sl_atr_mult    if sl_atr_mult    is not None else SL_ATR_MULT
    tp_mult  = tp_atr_mult    if tp_atr_mult    is not None else TP_ATR_MULT

    equity    = INITIAL_EQUITY
    trade_log = []

    atr_lookup = _compute_atr_lookup(df, atr_p)
    day_groups = {d: g for d, g in df.groupby(df.index.normalize())}
    dates      = sorted(day_groups.keys())

    for date in dates:
        day_df = day_groups[date]

        if len(day_df) < itsm_b + 2:
            continue

        # --- ITSM signal: bars 0 .. itsm_b-1 (no look-ahead) ---
        open_px  = day_df.iloc[0]['open']
        close_px = day_df.iloc[itsm_b - 1]['close']
        if open_px <= 0:
            continue

        r_open    = math.log(close_px / open_px)
        if abs(r_open) < itsm_thr:
            continue
        direction = 1 if r_open > 0 else -1

        # --- ATR-scaled stops ---
        atr_val   = atr_lookup.get(date, ATR_FALLBACK)
        sl_dist   = sl_mult * atr_val
        tp_dist   = tp_mult * atr_val
        contracts = max(1, math.floor(MAX_RISK_DOLLARS / (sl_dist * MULTIPLIER)))

        # --- Entry: open of bar[itsm_b] ---
        bars       = list(day_df.itertuples())
        entry_bar  = bars[itsm_b]
        entry_px   = entry_bar.open
        entry_time = entry_bar.Index
        sl_px      = entry_px - direction * sl_dist
        tp_px      = entry_px + direction * tp_dist

        # --- Scan for SL / TP / time exit ---
        exit_px     = None
        exit_time   = None
        exit_reason = None

        for bar in bars[itsm_b:]:
            bar_time = bar.Index

            time_exit = (
                bar_time.hour > EXIT_HOUR
                or (bar_time.hour == EXIT_HOUR
                    and bar_time.minute >= EXIT_MINUTE)
            )
            force_exit = (
                bar_time.hour > FORCE_EXIT_H
                or (bar_time.hour == FORCE_EXIT_H
                    and bar_time.minute >= FORCE_EXIT_M)
            )

            hit_sl = (direction == 1  and bar.low  <= sl_px) or \
                     (direction == -1 and bar.high >= sl_px)
            hit_tp = (direction == 1  and bar.high >= tp_px) or \
                     (direction == -1 and bar.low  <= tp_px)

            # Conservative: if both hit same bar, take the stop
            if hit_sl or (hit_sl and hit_tp):
                exit_px     = sl_px
                exit_reason = "SL"
            elif hit_tp:
                exit_px     = tp_px
                exit_reason = "TP"
            elif time_exit or force_exit:
                exit_px     = bar.close
                exit_reason = "TIME"
            else:
                continue

            exit_time = bar_time
            break

        if exit_px is None:
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
            "sl_pts":       round(sl_dist, 1),
            "tp_pts":       round(tp_dist, 1),
            "r_open":       round(r_open, 5),
            "pnl":          round(pnl, 2),
            "equity_after": round(equity, 2),
        })

    cols = [
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "atr", "sl_pts", "tp_pts",
        "r_open", "pnl", "equity_after",
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
