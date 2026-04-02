"""
strategy_gap_itsm.py
ITSM with Overnight Gap Confirmation + Volatility Regime Filter.

Academic basis
--------------
- ITSM direction (Notre Dame / Birmingham / AQR): first-30-min return predicts
  rest-of-day direction. Effect is documented to be stronger in high-vol regimes.
- Overnight gap direction: systematic continuation in equity index futures when
  both pre-market flow AND opening momentum agree (dual confirmation).

Regime-invariant design (addresses CSCV PBO = 60.6% in ITSM-ATR)
-----------------------------------------------------------------
- Gap confirm: BINARY filter -- no continuous threshold to overfit.
  Trade only when overnight gap direction == ITSM direction.
- Vol filter: trade only on HIGH-VOL days (ATR > rolling median ATR).
  ITSM academic evidence: effect is stronger in high-volatility regimes.
- ATR-scaled SL + TP: FIXED 2:1 RR (no free TP parameter).
- itsm_threshold FIXED at 0.002 -- not varied in CSCV.

CSCV grid (regime-invariant parameters only)
-------------------------------------------
  vol_lookback : rolling ATR median lookback (days) -- tests window robustness
  sl_atr_mult  : SL distance in ATR multiples      -- regime-invariant (scales with vol)
  (TP = 2 x SL fixed; threshold and itsm_bars fixed at academic defaults)
"""

import math
import numpy as np
import pandas as pd

INITIAL_EQUITY   = 50_000.0
MULTIPLIER       = 2
MAX_RISK_DOLLARS = 500

ITSM_BARS      = 6        # 6 x 5-min = 30-min opening window (academic spec)
ITSM_THRESHOLD = 0.002    # min |r_open| to trade (fixed, not varied in CSCV)
ATR_PERIOD     = 14
ATR_FALLBACK   = 200.0

SL_ATR_MULT    = 0.5
TP_RR          = 2.0      # TP = TP_RR x SL (fixed 2:1 RR, no free TP parameter)
VOL_LOOKBACK   = 63       # rolling median ATR lookback in trading days

EXIT_HOUR      = 15
EXIT_MINUTE    = 30
FORCE_EXIT_H   = 15
FORCE_EXIT_M   = 45


def _compute_atr_lookup(df: pd.DataFrame, atr_period: int) -> dict:
    """Rolling daily-range ATR. Strictly no look-ahead: today's range excluded."""
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


def _compute_vol_filter(atr_lookup: dict, vol_lookback: int) -> dict:
    """
    Returns {date -> bool}: True if today's ATR > rolling median of past vol_lookback days.
    No look-ahead: median computed from strictly past ATR values.
    Defaults True during warm-up (first vol_lookback days).
    """
    all_dates = sorted(atr_lookup.keys())
    atr_vals  = [atr_lookup[d] for d in all_dates]
    high_vol  = {}
    for i, d in enumerate(all_dates):
        if i < vol_lookback:
            high_vol[d] = True   # allow trading during warm-up
        else:
            past_atrs     = atr_vals[max(0, i - vol_lookback):i]
            median_atr    = float(np.median(past_atrs))
            high_vol[d]   = atr_lookup[d] > median_atr
    return high_vol


def _compute_prev_close(df: pd.DataFrame) -> dict:
    """Returns {date -> yesterday_session_close}."""
    day_closes = {}
    for d, g in df.groupby(df.index.normalize()):
        day_closes[d] = float(g['close'].iloc[-1])
    all_dates = sorted(day_closes.keys())
    prev_close = {}
    for i in range(1, len(all_dates)):
        prev_close[all_dates[i]] = day_closes[all_dates[i - 1]]
    return prev_close


def run_backtest(
    df: pd.DataFrame,
    itsm_bars: int        = None,
    itsm_threshold: float = None,
    atr_period: int       = None,
    sl_atr_mult: float    = None,
    vol_lookback: int         = None,
    require_gap_confirm: bool = True,
    require_high_vol: bool    = True,
    fixed_contracts: int      = None,
    norm_threshold_k: float   = None,
) -> tuple:
    """
    ITSM with overnight gap confirmation + volatility regime filter.

    Parameters
    ----------
    df              : 5-min OHLCV, timezone-aware ET index
    itsm_bars       : opening-window bars for ITSM signal (default 6 = 30 min)
    itsm_threshold  : min |r_open| to trade (default 0.002, fixed in CSCV)
    atr_period      : rolling ATR lookback in days (default 14, fixed in CSCV)
    sl_atr_mult     : SL distance in ATR multiples (default 0.5; CSCV dimension)
    vol_lookback    : rolling median ATR lookback for vol filter (default 63; CSCV dimension)
    fixed_contracts : if set, use this many contracts instead of risk-scaling
                      (Fix C: removes leverage differential between SL values)
    norm_threshold_k: if set, threshold = k * (atr_val / open_px) instead of fixed 0.002
                      (Fix B: require r_open proportionally large relative to daily noise)
                      Typical values: 0.10-0.25 (10-25% of daily ATR as min signal)
    """
    itsm_b   = itsm_bars      if itsm_bars      is not None else ITSM_BARS
    itsm_thr = itsm_threshold if itsm_threshold is not None else ITSM_THRESHOLD
    atr_p    = atr_period     if atr_period     is not None else ATR_PERIOD
    sl_mult  = sl_atr_mult    if sl_atr_mult    is not None else SL_ATR_MULT
    vol_lb   = vol_lookback   if vol_lookback   is not None else VOL_LOOKBACK

    equity    = INITIAL_EQUITY
    trade_log = []

    atr_lookup = _compute_atr_lookup(df, atr_p)
    vol_filter = _compute_vol_filter(atr_lookup, vol_lb)
    prev_close = _compute_prev_close(df)
    day_groups = {d: g for d, g in df.groupby(df.index.normalize())}
    dates      = sorted(day_groups.keys())

    for date in dates:
        day_df = day_groups[date]

        if len(day_df) < itsm_b + 2:
            continue

        # --- Vol regime filter: high-vol days only ---
        if require_high_vol and not vol_filter.get(date, True):
            continue

        # --- ITSM signal ---
        open_px  = day_df.iloc[0]['open']
        close_px = day_df.iloc[itsm_b - 1]['close']
        if open_px <= 0:
            continue
        r_open    = math.log(close_px / open_px)
        # Fix B: ATR-normalized threshold — require signal proportional to daily noise
        if norm_threshold_k is not None:
            atr_val_for_thr = atr_lookup.get(date, ATR_FALLBACK)
            effective_thr = norm_threshold_k * (atr_val_for_thr / open_px)
        else:
            effective_thr = itsm_thr
        if abs(r_open) < effective_thr:
            continue
        direction = 1 if r_open > 0 else -1

        # --- Overnight gap confirmation (binary, no continuous threshold) ---
        pc = prev_close.get(date)
        if require_gap_confirm and pc is not None and pc > 0:
            gap = open_px - pc
            # Skip if gap and ITSM disagree (conflicting signals)
            if (direction == 1 and gap < 0) or (direction == -1 and gap > 0):
                continue

        # --- ATR-scaled SL + TP (fixed 2:1 RR) ---
        atr_val   = atr_lookup.get(date, ATR_FALLBACK)
        sl_dist   = sl_mult * atr_val
        tp_dist   = TP_RR * sl_dist
        if fixed_contracts is not None:
            contracts = fixed_contracts
        else:
            contracts = max(1, math.floor(MAX_RISK_DOLLARS / (sl_dist * MULTIPLIER)))

        # --- Entry: open of bar[itsm_b] ---
        bars       = list(day_df.itertuples())
        entry_bar  = bars[itsm_b]
        entry_px   = entry_bar.open
        entry_time = entry_bar.Index
        sl_px      = entry_px - direction * sl_dist
        tp_px      = entry_px + direction * tp_dist

        # --- Scan for SL / TP / time exit ---
        exit_px = exit_time = exit_reason = None

        for bar in bars[itsm_b:]:
            bar_time = bar.Index
            time_exit = (bar_time.hour > EXIT_HOUR or
                         (bar_time.hour == EXIT_HOUR and bar_time.minute >= EXIT_MINUTE))
            force_exit = (bar_time.hour > FORCE_EXIT_H or
                          (bar_time.hour == FORCE_EXIT_H and bar_time.minute >= FORCE_EXIT_M))
            hit_sl = ((direction == 1  and bar.low  <= sl_px) or
                      (direction == -1 and bar.high >= sl_px))
            hit_tp = ((direction == 1  and bar.high >= tp_px) or
                      (direction == -1 and bar.low  <= tp_px))
            if hit_sl or (hit_sl and hit_tp):
                exit_px, exit_reason = sl_px, "SL"
            elif hit_tp:
                exit_px, exit_reason = tp_px, "TP"
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
            "date":          date.date(),
            "direction":     "LONG" if direction == 1 else "SHORT",
            "entry_time":    entry_time,
            "exit_time":     exit_time,
            "exit_reason":   exit_reason,
            "entry_price":   round(entry_px, 2),
            "exit_price":    round(exit_px, 2),
            "contracts":     contracts,
            "atr":           round(atr_val, 1),
            "sl_pts":        round(sl_dist, 1),
            "tp_pts":        round(tp_dist, 1),
            "r_open":        round(r_open, 5),
            "overnight_gap": round(open_px - pc, 2) if (pc and pc > 0) else 0.0,
            "pnl":           round(pnl, 2),
            "equity_after":  round(equity, 2),
        })

    cols = [
        "date", "direction", "entry_time", "exit_time", "exit_reason",
        "entry_price", "exit_price", "contracts", "atr", "sl_pts", "tp_pts",
        "r_open", "overnight_gap", "pnl", "equity_after",
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
