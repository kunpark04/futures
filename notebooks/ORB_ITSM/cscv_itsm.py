"""
cscv_itsm.py
CSCV / PBO overfitting test wired to strategy_itsm.run_backtest().

Exports the same API as the project-level cscv.py:
    build_pnl_matrix(df, variants)
    run_cscv(M, S=16)
    sharpe_cols(M)
    pbo_verdict(pbo)

The only difference: build_pnl_matrix here accepts ITSM-specific variant
keys (use_itsm_filter, itsm_threshold, skip_mon_fri) in addition to the
standard ORB keys.
"""

import itertools
import numpy as np
import pandas as pd

from strategy_itsm import run_backtest

ALLOWED_KEYS = {
    'sl_points', 'tp_points', 'or_bars', 'ema_period',
    'rsi_long_min', 'rsi_short_max',
    'use_itsm_filter', 'itsm_threshold', 'skip_mon_fri',
}


def build_pnl_matrix(df: pd.DataFrame, variants: list) -> tuple:
    """
    Run each variant on df and return a T x N daily P&L matrix.

    Parameters
    ----------
    df       : 5-min OHLCV dataframe
    variants : list of dicts with any keys from ALLOWED_KEYS

    Returns
    -------
    M     : np.ndarray (T, N)
    dates : pd.DatetimeIndex
    """
    series_list = []
    for idx, v in enumerate(variants):
        kwargs = {k: v[k] for k in v if k in ALLOWED_KEYS}
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


def sharpe_cols(matrix: np.ndarray) -> np.ndarray:
    means = matrix.mean(axis=0)
    stds  = matrix.std(axis=0, ddof=1)
    with np.errstate(invalid='ignore', divide='ignore'):
        sr = np.where(stds > 0, means / stds * np.sqrt(252), 0.0)
    return sr


def run_cscv(M: np.ndarray, S: int = 16) -> dict:
    if S % 2 != 0:
        raise ValueError(f'S must be even, got S={S}')

    T_orig, N = M.shape
    T_trim = (T_orig // S) * S
    M = M[:T_trim]
    chunk = T_trim // S

    chunks  = [M[i * chunk : (i + 1) * chunk] for i in range(S)]
    all_idx = list(range(S))

    logits            = []
    is_sharpes        = []
    oos_sharpes       = []
    selected_variants = []

    for is_idx in itertools.combinations(all_idx, S // 2):
        oos_idx = [i for i in all_idx if i not in is_idx]

        IS  = np.vstack([chunks[i] for i in is_idx])
        OOS = np.vstack([chunks[i] for i in oos_idx])

        is_sr  = sharpe_cols(IS)
        oos_sr = sharpe_cols(OOS)

        n_star   = int(np.argmax(is_sr))
        oos_rank = float(np.sum(oos_sr <= oos_sr[n_star]))
        omega    = np.clip(oos_rank / (N + 1), 1e-7, 1 - 1e-7)
        lam      = float(np.log(omega / (1.0 - omega)))

        logits.append(lam)
        is_sharpes.append(is_sr[n_star])
        oos_sharpes.append(oos_sr[n_star])
        selected_variants.append(n_star)

    return {
        'pbo':               float(np.mean(np.array(logits) < 0)),
        'logits':            np.array(logits),
        'is_sharpes':        np.array(is_sharpes),
        'oos_sharpes':       np.array(oos_sharpes),
        'selected_variants': np.array(selected_variants),
        'n_combos':          len(logits),
        'S':                 S,
        'N':                 N,
        'T':                 T_trim,
    }


def pbo_verdict(pbo: float) -> str:
    if pbo < 0.05:
        return 'NOT OVERFIT (PBO < 5%)'
    elif pbo < 0.20:
        return 'LOW OVERFITTING RISK (PBO 5-20%)'
    elif pbo < 0.50:
        return 'MODERATE OVERFITTING RISK (PBO 20-50%)'
    else:
        return 'HIGH OVERFITTING RISK (PBO >= 50%)'
