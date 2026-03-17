"""
strategy.py
Opening Range Breakout (ORB) + EMA-20 trend filter strategy for NQ futures.

Rules
-----
- Opening Range  : first OR_BARS × 5-min bars (09:30–10:00 AM ET)
- Long  entry    : close > OR_high  AND  close > EMA20
- Short entry    : close < OR_low   AND  close < EMA20
- Entry          : open of the NEXT bar after signal
- Stop Loss      : 2% from entry price
- Take Profit    : 4% from entry price
- Max risk/trade : < 5% of current equity
- Force exit     : 15:45 ET bar close
- One trade/day  : first valid signal only
- No overnight   : all positions closed before 16:00 ET
"""

import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
INITIAL_EQUITY    = 50_000.0
MULTIPLIER        = 2          # MNQ micro NQ: $2 per index point
MAX_RISK_DOLLARS  = 500        # max dollar loss per trade at the stop
SL_POINTS         = 60         # stop loss  60 NQ index points (~0.3% of price)
TP_POINTS         = 120        # take profit 120 NQ index points (2:1 RR)
TRAILING_STOP_BE  = False      # move SL to break-even once 1R (SL_POINTS) profit reached
                               # Tested on 11yr dataset: BE hurts (-$30k, win rate 44.7%->38.8%)
                               # Set True to re-test; pass trailing_stop_be= to run_backtest()
OR_BARS         = 6          # 6 × 5-min = 30-min opening range
EMA_PERIOD      = 20
RSI_PERIOD      = 14
RSI_LONG_MIN    = 52         # RSI must be above this to take a long
RSI_SHORT_MAX   = 48         # RSI must be below this to take a short
ENTRY_CUTOFF_H  = 15
ENTRY_CUTOFF_M  = 30         # no new entries after 15:30
FORCE_EXIT_H    = 15
FORCE_EXIT_M    = 45         # force close at 15:45


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (pandas ewm, adjust=False)."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder RSI using exponential smoothing (standard formula)."""
    delta = series.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _compute_daily_or(day_df: pd.DataFrame) -> tuple:
    """
    Return (or_high, or_low) from the first OR_BARS bars of the session.
    Returns (None, None) if the session has fewer bars than OR_BARS.
    """
    if len(day_df) < OR_BARS:
        return None, None
    opening_bars = day_df.iloc[:OR_BARS]
    return opening_bars["high"].max(), opening_bars["low"].min()


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def _calc_contracts(equity: float) -> int:
    """
    Determine number of MNQ micro contracts to trade.

    Sized so that a full stop-out (SL_POINTS) loses no more than
    RISK_PCT of current equity.  Minimum 1 contract.
    """
    risk_dollars      = MAX_RISK_DOLLARS           # fixed $500 max loss per trade
    risk_per_contract = SL_POINTS * MULTIPLIER     # $ lost per contract at stop
    if risk_per_contract <= 0:
        return 1
    contracts = math.floor(risk_dollars / risk_per_contract)
    return max(1, contracts)


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------

def run_backtest(df: pd.DataFrame, trailing_stop_be: bool = TRAILING_STOP_BE) -> tuple:
    """
    Run the ORB + EMA-20 backtest over all days in df.

    Parameters
    ----------
    df : pd.DataFrame
        5-min OHLCV data with a timezone-aware datetime index (US/Eastern).
        Must have columns: open, high, low, close, volume.
    trailing_stop_be : bool
        If True, move SL to entry price (break-even) once the trade
        reaches SL_POINTS profit (1R). Defaults to TRAILING_STOP_BE constant.

    Returns
    -------
    trades : pd.DataFrame
        One row per completed trade with columns:
        date, direction, entry_time, exit_time, exit_reason,
        entry_price, exit_price, contracts, pnl, equity_after, be_triggered
    equity_curve : pd.Series
        Equity value at the close of each calendar date.
    """
    equity    = INITIAL_EQUITY
    trade_log = []

    # Compute indicators on the full dataset so EMA and RSI are properly
    # warmed up across sessions (not reset to cold start each day).
    df = df.copy()
    df["ema20"] = _ema(df["close"], EMA_PERIOD)
    df["rsi"]   = _rsi(df["close"], RSI_PERIOD)

    # Group bars by calendar date
    dates = sorted(df.index.normalize().unique())

    for date in dates:
        day_df = df[df.index.normalize() == date].copy()

        # Need at least OR_BARS + 1 extra bar to trade
        if len(day_df) <= OR_BARS:
            continue

        # ── Opening range ──────────────────────────────────────────────────
        or_high, or_low = _compute_daily_or(day_df)
        if or_high is None:
            continue

        # ── Scan for entry signal (first one wins) ─────────────────────────
        in_trade     = False
        trade_dir    = 0      # +1 long, -1 short
        entry_px     = 0.0
        sl_px        = 0.0
        tp_px        = 0.0
        contracts    = 1
        entry_time   = None
        be_triggered = False  # has SL been moved to break-even?

        bars = list(day_df.itertuples())
        n    = len(bars)

        for i, bar in enumerate(bars):
            bar_time = bar.Index

            # Skip the opening range bars for signal generation
            if i < OR_BARS:
                continue

            # ── While in a trade, check exits ──────────────────────────────
            if in_trade:
                force_exit = (
                    bar_time.hour > FORCE_EXIT_H
                    or (bar_time.hour == FORCE_EXIT_H
                        and bar_time.minute >= FORCE_EXIT_M)
                )

                # Move SL to break-even once 1R profit is reached
                if trailing_stop_be and not be_triggered:
                    one_r_reached = (
                        (trade_dir == 1  and bar.high - entry_px >= SL_POINTS) or
                        (trade_dir == -1 and entry_px - bar.low  >= SL_POINTS)
                    )
                    if one_r_reached:
                        sl_px        = entry_px
                        be_triggered = True

                hit_sl = (trade_dir == 1 and bar.low  <= sl_px) or \
                         (trade_dir == -1 and bar.high >= sl_px)
                hit_tp = (trade_dir == 1 and bar.high >= tp_px) or \
                         (trade_dir == -1 and bar.low  <= tp_px)

                # Conservative: if both hit same bar, take the stop
                if hit_sl or (hit_sl and hit_tp):
                    exit_px     = sl_px
                    exit_reason = "SL"
                elif hit_tp:
                    exit_px     = tp_px
                    exit_reason = "TP"
                elif force_exit:
                    exit_px     = bar.close
                    exit_reason = "EOD"
                else:
                    continue  # still in trade, no exit yet

                # Record trade
                points = (exit_px - entry_px) * trade_dir
                pnl    = points * MULTIPLIER * contracts
                equity += pnl

                trade_log.append({
                    "date":         date.date(),
                    "direction":    "LONG" if trade_dir == 1 else "SHORT",
                    "entry_time":   entry_time,
                    "exit_time":    bar_time,
                    "exit_reason":  exit_reason,
                    "entry_price":  round(entry_px, 2),
                    "exit_price":   round(exit_px, 2),
                    "contracts":    contracts,
                    "pnl":          round(pnl, 2),
                    "equity_after": round(equity, 2),
                    "be_triggered": be_triggered,
                })
                in_trade = False
                break  # one trade per day

            # ── Not in trade — look for entry signal ───────────────────────
            past_cutoff = (
                bar_time.hour > ENTRY_CUTOFF_H
                or (bar_time.hour == ENTRY_CUTOFF_H
                    and bar_time.minute >= ENTRY_CUTOFF_M)
            )
            if past_cutoff:
                break

            ema20 = bar.ema20
            rsi   = bar.rsi

            long_signal  = (bar.close > or_high) and (bar.close > ema20) and (rsi > RSI_LONG_MIN)
            short_signal = (bar.close < or_low)  and (bar.close < ema20) and (rsi < RSI_SHORT_MAX)

            if not (long_signal or short_signal):
                continue

            # Entry on next bar's open
            if i + 1 >= n:
                break
            next_bar = bars[i + 1]

            trade_dir    = 1 if long_signal else -1
            entry_px     = next_bar.open
            sl_px        = entry_px - SL_POINTS * trade_dir
            tp_px        = entry_px + TP_POINTS * trade_dir
            contracts    = _calc_contracts(equity)
            entry_time   = next_bar.Index
            be_triggered = False
            in_trade     = True
            i           += 1   # skip next bar (it's now the entry bar)

    # Build outputs
    trades = pd.DataFrame(trade_log) if trade_log else pd.DataFrame(columns=[
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "pnl", "equity_after", "be_triggered",
    ])

    # Equity curve: daily equity snapshots
    if not trades.empty:
        eq = trades.set_index("date")["equity_after"]
        eq.index = pd.to_datetime(eq.index)
        # Fill forward so every date has a value
        all_dates   = pd.date_range(eq.index.min(), eq.index.max(), freq="B")
        equity_curve = eq.reindex(all_dates).ffill().fillna(INITIAL_EQUITY)
        equity_curve.name = "equity"
    else:
        equity_curve = pd.Series(
            [INITIAL_EQUITY],
            index=pd.to_datetime([pd.Timestamp.today().normalize()]),
            name="equity",
        )

    return trades, equity_curve
