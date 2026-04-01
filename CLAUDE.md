# Futures_v2 — Project Instructions

## Project Overview
Intraday NQ futures (E-mini Nasdaq-100) trading strategy backtester.
- **Strategy:** Opening Range Breakout (ORB) + EMA-20 + RSI-14 filter
- **Timeframe:** 5-minute bars
- **Data source:** Yahoo Finance via yfinance (ticker: NQ=F, 60-day max)
- **Account:** $50,000 initial equity
- **Risk:** $500 max loss per trade | SL: 60 pts | TP: 120 pts (2:1 RR)
- **Contract:** MNQ Micro ($2/point) | No overnight positions

## File Structure
- `data_fetch.py`              — pulls NQ=F 5-min data via yfinance, caches to data/NQ_5m.csv
- `strategy.py`                — ORB signal logic, indicators, position sizing, backtest engine
- `cscv.py`                    — CSCV/PBO overfitting test (build_pnl_matrix, run_cscv, sharpe_cols, pbo_verdict)
- `analysis.py`                — performance metrics and chart generation (saved to output/)
- `main.py`                    — CLI entry point: python main.py [--refresh]
- `research/`                  — reference papers (backtest-prob.pdf, backtest-prob.md)
- `notebooks/original/backtest.ipynb`         — v1 notebook (original, price-% stops, no RSI)
- `notebooks/original/backtest_v2.ipynb`      — v2 notebook with changelog and exit breakdown
- `notebooks/original/backtest_v3.ipynb`      — v3 notebook: trailing stop BE comparison
- `notebooks/original/backtest_v4.ipynb`      — v4 notebook: CSCV/PBO overfitting test
- `notebooks/original/root_cause_analysis_v2.ipynb` — RCA: volume filter + trailing stop analysis
- `notebooks/original/root_cause_analysis_v3.ipynb` — RCA v3 (in progress)

## Allowed Libraries
**Third-party:** numpy, pandas, matplotlib, seaborn, yfinance
**Standard library only (no pip):** os, sys, math, urllib, json, datetime
Do not add any new third-party libraries without asking the user first.

## Strategy Parameters (strategy.py)
All key parameters are constants at the top of strategy.py:
- `INITIAL_EQUITY`, `MAX_RISK_DOLLARS`, `MULTIPLIER`
- `SL_POINTS`, `TP_POINTS`
- `OR_BARS`, `EMA_PERIOD`, `RSI_PERIOD`, `RSI_LONG_MIN`, `RSI_SHORT_MAX`
- `ENTRY_CUTOFF_H/M`, `FORCE_EXIT_H/M`

## Performance Targets
**Goal: Beat the S&P 500** — every backtest must pass:
- Win rate >= 50%
- Sharpe ratio > 1.0 (vs S&P 500 ~0.6, CAGR ~10-11%)

## S&P 500 Benchmark Rule
Every performance metric table, chart, and equity curve must include S&P 500 as a benchmark column/series.
Reference values for Dec 2014 - Mar 2026:
- Sharpe: ~0.6 | Max Drawdown: ~55% | Total Return: ~170% | CAGR: ~10-11%

## Coding Rules
- **Enter plan mode before writing any code** — always plan first, implement second
- Do not hold positions overnight — all trades must exit by 15:45 ET
- Indicators (EMA, RSI) must be computed on the full dataset, not reset per day (cold-start bias: RSI takes 14+ bars to converge)
- SL/TP must use absolute points, never price % (2% of NQ ~21k = 420 pts — wider than the entire daily range)
- SL/TP checks use bar high/low; if both hit in the same bar, take the SL (conservative)
- One trade per day — first valid signal only
- Entry is on the open of the bar after the signal bar

## Known Pitfalls (do not repeat these mistakes)
- **Windows cp1252 encoding.** Avoid Unicode characters (arrows ->, box-drawing chars)
  in print statements — use plain ASCII instead.
- **Modifying loop variable `i` inside a for loop has no effect in Python.** Use
  a while loop or index manually if you need to skip iterations.
- **yfinance CSV cache reload.** When reading cached CSV back, use:
  `df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")`
  Plain `pd.to_datetime` drops timezone info and breaks session filtering.
- **Relative paths in data_fetch.py break when notebooks set CWD.** Use `__file__`-relative
  paths (`os.path.dirname(os.path.abspath(__file__))`) in any module that reads/writes
  `data/NQ_5m.csv`, so notebooks always load from the project root regardless of their CWD.

## Position Sizing Logic
```
risk_per_contract = SL_POINTS * MULTIPLIER      # 60 * $2 = $120
contracts         = floor(MAX_RISK_DOLLARS / risk_per_contract)  # floor(500/120) = 4
```
Max loss per trade is capped at $500 regardless of equity size.

## CSCV / PBO Findings (backtest_v4.ipynb)
Tested overfitting across 60 parameter variants (SL/TP x OR_BARS x EMA_PERIOD), S=16 splits, 12,870 combinations.

**Key results:**
- PBO = 47.7% — MODERATE overfitting risk (threshold: <5% = not overfit, >50% = high risk)
- Prob(loss OOS) = 1.4% — the ORB edge is genuine; strategy profitable on unseen data
- Median IS Sharpe: 1.097 -> Median OOS Sharpe: 0.717 (~35% degradation)
- Forward Sharpe estimate: ~0.72 (realistic expectation, still beats S&P 500 ~0.60)
- Baseline v3 params rank 48/60 — not the global optimum
- Best variant found: SL=70, TP=140, OR=8bars, EMA=10 (Sharpe 0.990 full dataset)

**Conclusion:** The strategy has genuine edge but specific parameter choices carry moderate overfitting risk.
The v3 parameters are not the global optimum. Candidate for v5: SL=70/TP=140/OR=8/EMA=10 — rerun CSCV to confirm.

**run_backtest() now accepts keyword overrides:** sl_points, tp_points, or_bars, ema_period, rsi_long_min, rsi_short_max

## Root Cause Analysis Findings (root_cause_analysis_v2.ipynb)
Two improvement areas were researched against v2 trade data:

**#1 Volume Confirmation — DISCARDED**
- Hypothesis: high-volume breakouts have higher win rate than low-volume ones
- Finding: low-volume trades had an 88.9% win rate and $4,442 P&L — outperformed high-vol
- Conclusion: volume filter removes the best trades. Do not implement.

**#4 Trailing Stop to Break-Even — IMPLEMENTED & TESTED (backtest_v3.ipynb)**
- Implemented as `run_backtest(df, trailing_stop_be=True/False)` toggle
- Default: `TRAILING_STOP_BE = False` (BE hurts on full dataset)
- Full 11yr test (2,740 trades): BE win rate 38.8% vs baseline 44.7%, PnL $44.8k vs $74.9k (-$30k)
- Root cause: BE triggered on 845 trades (31%); many trades oscillate to entry before hitting TP
- RCA v2 finding (+$960) was based on only 2 trades — insufficient sample size
- Conclusion: do NOT use trailing stop to BE with this strategy's 60pt SL / 120pt TP parameters

## After Every Backtest Iteration
1. Update this CLAUDE.md with any new learnings, pitfalls, or parameter changes
2. Update tasks/lessons.md with any mistakes made during the session
3. Push all changed files to GitHub:
```bash
git add .
git commit -m "brief description of changes"
git push origin main
```

## GitHub
Repository: https://github.com/kunpark04/futures
