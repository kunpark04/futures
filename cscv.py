"""
cscv.py
Combinatorially Symmetric Cross-Validation (CSCV) for Probability of Backtest Overfitting (PBO).

Reference: Bailey, Borwein, Lopez de Prado, Zhu (2015)
  "The Probability of Backtest Overfitting"

Usage
-----
    from cscv import build_pnl_matrix, run_cscv

    M, dates = build_pnl_matrix(df, variants)   # (T x N) daily P&L matrix
    results  = run_cscv(M)                       # dict with pbo, logits, etc.
"""

import itertools
import numpy as np
import pandas as pd

from strategy import run_backtest


# ---------------------------------------------------------------------------
# Build P&L matrix
# ---------------------------------------------------------------------------

def build_pnl_matrix(df: pd.DataFrame, variants: list) -> tuple:
    """
    Run each strategy variant on df and build a T x N daily P&L matrix.

    Parameters
    ----------
    df       : 5-min OHLCV dataframe (full dataset)
    variants : list of dicts, each with keys matching run_backtest() kwargs:
               sl_points, tp_points, or_bars, ema_period, rsi_long_min, rsi_short_max

    Returns
    -------
    M     : np.ndarray shape (T, N)  daily P&L — rows = trading days, cols = variants
    dates : pd.DatetimeIndex         the T trading days (row labels)
    """
    allowed_keys = {'sl_points', 'tp_points', 'or_bars', 'ema_period',
                    'rsi_long_min', 'rsi_short_max'}

    series_list = []
    for idx, v in enumerate(variants):
        kwargs = {k: v[k] for k in v if k in allowed_keys}
        trades, _ = run_backtest(df, **kwargs)

        if trades.empty:
            series_list.append(pd.Series(dtype=float, name=idx))
        else:
            s = trades.groupby('date')['pnl'].sum()
            s.index = pd.to_datetime(s.index)
            s.name = idx
            series_list.append(s)

        if (idx + 1) % 10 == 0:
            print(f'  {idx + 1}/{len(variants)} variants complete...')

    all_dates = sorted(set().union(*[set(s.index) for s in series_list]))
    M_df = pd.DataFrame(index=all_dates)
    for s in series_list:
        M_df[s.name] = s
    M_df = M_df.fillna(0.0).sort_index()

    return M_df.values, M_df.index


# ---------------------------------------------------------------------------
# CSCV core
# ---------------------------------------------------------------------------

def sharpe_cols(matrix: np.ndarray) -> np.ndarray:
    """
    Annualized Sharpe ratio for each column. Returns array of shape (N,).
    Uses ddof=1. Returns 0 for columns with zero std.
    """
    means = matrix.mean(axis=0)
    stds  = matrix.std(axis=0, ddof=1)
    with np.errstate(invalid='ignore', divide='ignore'):
        sr = np.where(stds > 0, means / stds * np.sqrt(252), 0.0)
    return sr


def run_cscv(M: np.ndarray, S: int = 16) -> dict:
    """
    Combinatorially Symmetric Cross-Validation.

    Parameters
    ----------
    M : np.ndarray shape (T, N)
        Daily P&L matrix — T trading days, N strategy variants.
    S : int
        Number of equal splits (must be even). S=16 gives C(16,8)=12,870 combinations.

    Returns
    -------
    dict with keys:
        pbo                : float    Probability of Backtest Overfitting
        logits             : ndarray  logit of OOS rank per combination
        is_sharpes         : ndarray  IS Sharpe of best IS strategy per combination
        oos_sharpes        : ndarray  OOS Sharpe of that strategy per combination
        selected_variants  : ndarray  index (0..N-1) of IS winner per combination
        n_combos           : int      total combinations evaluated
        S                  : int      splits used
        N                  : int      number of strategy variants
        T                  : int      number of trading days (after trim)
    """
    if S % 2 != 0:
        raise ValueError(f'S must be even, got S={S}')

    T_orig, N = M.shape
    T_trim = (T_orig // S) * S
    M = M[:T_trim]
    chunk = T_trim // S

    chunks  = [M[i * chunk : (i + 1) * chunk] for i in range(S)]
    all_idx = list(range(S))

    logits             = []
    is_sharpes         = []
    oos_sharpes        = []
    selected_variants  = []

    for is_idx in itertools.combinations(all_idx, S // 2):
        oos_idx = [i for i in all_idx if i not in is_idx]

        IS  = np.vstack([chunks[i] for i in is_idx])
        OOS = np.vstack([chunks[i] for i in oos_idx])

        is_sr  = sharpe_cols(IS)
        oos_sr = sharpe_cols(OOS)

        n_star   = int(np.argmax(is_sr))
        oos_rank = float(np.sum(oos_sr <= oos_sr[n_star]))  # 1..N
        omega    = np.clip(oos_rank / (N + 1), 1e-7, 1 - 1e-7)
        lam      = float(np.log(omega / (1.0 - omega)))

        logits.append(lam)
        is_sharpes.append(is_sr[n_star])
        oos_sharpes.append(oos_sr[n_star])
        selected_variants.append(n_star)

    logits            = np.array(logits)
    is_sharpes        = np.array(is_sharpes)
    oos_sharpes       = np.array(oos_sharpes)
    selected_variants = np.array(selected_variants)

    return {
        'pbo':                float(np.mean(logits < 0)),
        'logits':             logits,
        'is_sharpes':         is_sharpes,
        'oos_sharpes':        oos_sharpes,
        'selected_variants':  selected_variants,
        'n_combos':           len(logits),
        'S':                  S,
        'N':                  N,
        'T':                  T_trim,
    }


# ---------------------------------------------------------------------------
# Convenience: PBO verdict string
# ---------------------------------------------------------------------------

def pbo_verdict(pbo: float) -> str:
    if pbo < 0.05:
        return 'NOT OVERFIT (PBO < 5%)'
    elif pbo < 0.20:
        return 'LOW OVERFITTING RISK (PBO 5-20%)'
    elif pbo < 0.50:
        return 'MODERATE OVERFITTING RISK (PBO 20-50%)'
    else:
        return 'HIGH OVERFITTING RISK (PBO >= 50%)'
