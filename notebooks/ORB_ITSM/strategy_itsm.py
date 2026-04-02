"""
strategy_itsm.py
ORB + ITSM (Intraday Time-Series Momentum) confluence strategy for NQ futures.

Changes from strategy.py (original ORB):
- Added _itsm_direction() helper: computes first-30-min momentum direction
- Added use_itsm_filter, itsm_threshold, skip_mon_fri kwargs to run_backtest()
- v5 default parameters: SL=70, TP=140, OR=8, EMA=10

No look-ahead bias: ITSM confirmed at 10:00 (bar 5 close); OR=8 ends at 10:10;
earliest entry is 10:15.
"""

import math
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration (v5 defaults — CSCV best variant, OOS success rate 84.8%)
# ---------------------------------------------------------------------------
INITIAL_EQUITY    = 50_000.0
MULTIPLIER        = 2          # MNQ micro NQ: $2 per index point
MAX_RISK_DOLLARS  = 500        # max dollar loss per trade at the stop
SL_POINTS         = 70         # stop loss 70 NQ index points
TP_POINTS         = 140        # take profit 140 NQ index points (2:1 RR)
TRAILING_STOP_BE  = False
OR_BARS           = 8          # 8 x 5-min = 40-min opening range (9:30-10:10)
EMA_PERIOD        = 10
RSI_PERIOD        = 14
RSI_LONG_MIN      = 52
RSI_SHORT_MAX     = 48
ENTRY_CUTOFF_H    = 14
ENTRY_CUTOFF_M    = 30         # no new entries after 14:30 (needs runway to TP)
FORCE_EXIT_H      = 15
FORCE_EXIT_M      = 45         # force close at 15:45

USE_ITSM_FILTER   = False      # require ITSM confluence (off by default)
ITSM_THRESHOLD    = 0.0        # min |r_open| to fire ITSM signal (0.0 = always)
SKIP_MON_FRI      = False      # skip Monday and Friday


# ---------------------------------------------------------------------------
# Indicator helpers
# ---------------------------------------------------------------------------

def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def _compute_daily_or(day_df: pd.DataFrame, or_bars: int) -> tuple:
    if len(day_df) < or_bars:
        return None, None
    opening_bars = day_df.iloc[:or_bars]
    return opening_bars["high"].max(), opening_bars["low"].min()


def _itsm_direction(day_df: pd.DataFrame, threshold: float = 0.0) -> int:
    """
    Intraday Time-Series Momentum direction.

    Uses the first 6 bars (9:30-9:55) to compute the 30-min return:
        r_open = close[bar5] / open[bar0] - 1

    Returns +1 (up), -1 (down), or 0 if |r_open| < threshold.
    Returns 0 if the day has fewer than 6 bars.

    No look-ahead: bar5 closes at 10:00, before OR=8 ends at 10:10.
    """
    if len(day_df) < 6:
        return 0
    open_price  = day_df.iloc[0]["open"]
    close_10    = day_df.iloc[5]["close"]   # close of 9:55 bar = price at 10:00
    if open_price == 0:
        return 0
    r_open = close_10 / open_price - 1
    if abs(r_open) < threshold:
        return 0
    return 1 if r_open > 0 else -1


# ---------------------------------------------------------------------------
# Position sizing
# ---------------------------------------------------------------------------

def _calc_contracts(equity: float, sl_pts: int = SL_POINTS) -> int:
    risk_per_contract = sl_pts * MULTIPLIER
    if risk_per_contract <= 0:
        return 1
    return max(1, math.floor(MAX_RISK_DOLLARS / risk_per_contract))


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    trailing_stop_be: bool = TRAILING_STOP_BE,
    sl_points: int = None,
    tp_points: int = None,
    or_bars: int = None,
    ema_period: int = None,
    rsi_long_min: float = None,
    rsi_short_max: float = None,
    use_itsm_filter: bool = USE_ITSM_FILTER,
    itsm_threshold: float = ITSM_THRESHOLD,
    skip_mon_fri: bool = SKIP_MON_FRI,
) -> tuple:
    """
    Run the ORB + ITSM backtest over all days in df.

    Parameters
    ----------
    df : pd.DataFrame
        5-min OHLCV data with a timezone-aware datetime index (US/Eastern).
    use_itsm_filter : bool
        If True, only take ORB signals that agree with first-30-min momentum.
    itsm_threshold : float
        Minimum absolute first-30-min return to act on ITSM direction.
        0.0 means any non-zero return fires. Example: 0.001 = 0.1%.
    skip_mon_fri : bool
        If True, skip all Monday (dow=0) and Friday (dow=4) sessions.

    Returns
    -------
    trades : pd.DataFrame
    equity_curve : pd.Series
    """
    sl_pts     = sl_points    if sl_points    is not None else SL_POINTS
    tp_pts     = tp_points    if tp_points    is not None else TP_POINTS
    orb        = or_bars      if or_bars      is not None else OR_BARS
    ema_p      = ema_period   if ema_period   is not None else EMA_PERIOD
    rsi_lo_min = rsi_long_min  if rsi_long_min  is not None else RSI_LONG_MIN
    rsi_sh_max = rsi_short_max if rsi_short_max is not None else RSI_SHORT_MAX

    equity    = INITIAL_EQUITY
    trade_log = []

    df = df.copy()
    df["ema"] = _ema(df["close"], ema_p)
    df["rsi"] = _rsi(df["close"], RSI_PERIOD)

    day_groups = {d: g for d, g in df.groupby(df.index.normalize())}
    dates = sorted(day_groups.keys())

    for date in dates:
        day_df = day_groups[date].copy()

        # Skip Monday (0) and Friday (4) if requested
        if skip_mon_fri and date.dayofweek in (0, 4):
            continue

        if len(day_df) <= orb:
            continue

        or_high, or_low = _compute_daily_or(day_df, orb)
        if or_high is None:
            continue

        # ITSM direction for the day (uses bars 0-5 only — confirmed at 10:00)
        itsm_dir = _itsm_direction(day_df, itsm_threshold) if use_itsm_filter else 0

        in_trade     = False
        trade_dir    = 0
        entry_px     = 0.0
        sl_px        = 0.0
        tp_px        = 0.0
        contracts    = 1
        entry_time   = None
        be_triggered = False

        bars = list(day_df.itertuples())
        n    = len(bars)

        for i, bar in enumerate(bars):
            bar_time = bar.Index

            if i < orb:
                continue

            if in_trade:
                force_exit = (
                    bar_time.hour > FORCE_EXIT_H
                    or (bar_time.hour == FORCE_EXIT_H
                        and bar_time.minute >= FORCE_EXIT_M)
                )

                if trailing_stop_be and not be_triggered:
                    one_r_reached = (
                        (trade_dir == 1  and bar.high - entry_px >= sl_pts) or
                        (trade_dir == -1 and entry_px - bar.low  >= sl_pts)
                    )
                    if one_r_reached:
                        sl_px        = entry_px
                        be_triggered = True

                hit_sl = (trade_dir == 1 and bar.low  <= sl_px) or \
                         (trade_dir == -1 and bar.high >= sl_px)
                hit_tp = (trade_dir == 1 and bar.high >= tp_px) or \
                         (trade_dir == -1 and bar.low  <= tp_px)

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
                    continue

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
                    "itsm_dir":     itsm_dir,
                })
                in_trade = False
                break

            past_cutoff = (
                bar_time.hour > ENTRY_CUTOFF_H
                or (bar_time.hour == ENTRY_CUTOFF_H
                    and bar_time.minute >= ENTRY_CUTOFF_M)
            )
            if past_cutoff:
                break

            ema_val = bar.ema
            rsi_val = bar.rsi

            long_signal  = (bar.close > or_high) and (bar.close > ema_val) and (rsi_val > rsi_lo_min)
            short_signal = (bar.close < or_low)  and (bar.close < ema_val) and (rsi_val < rsi_sh_max)

            # Apply ITSM filter if enabled
            if use_itsm_filter:
                long_signal  = long_signal  and (itsm_dir == 1)
                short_signal = short_signal and (itsm_dir == -1)

            if not (long_signal or short_signal):
                continue

            if i + 1 >= n:
                break
            next_bar = bars[i + 1]

            trade_dir    = 1 if long_signal else -1
            entry_px     = next_bar.open
            sl_px        = entry_px - sl_pts * trade_dir
            tp_px        = entry_px + tp_pts * trade_dir
            contracts    = _calc_contracts(equity, sl_pts)
            entry_time   = next_bar.Index
            be_triggered = False
            in_trade     = True
            i           += 1

    trades = pd.DataFrame(trade_log) if trade_log else pd.DataFrame(columns=[
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "pnl", "equity_after",
        "be_triggered", "itsm_dir",
    ])

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
