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
- `data_fetch.py`     — pulls NQ=F 5-min data via yfinance, caches to data/NQ_5m.csv
- `strategy.py`       — ORB signal logic, indicators, position sizing, backtest engine
- `analysis.py`       — performance metrics and chart generation (saved to output/)
- `main.py`           — CLI entry point: python main.py [--refresh]
- `backtest.ipynb`    — v1 notebook (original)
- `backtest_v2.ipynb` — v2 notebook with changelog and exit breakdown

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
Every backtest must be checked against:
- Win rate ≥ 50%
- Sharpe ratio > 1.0

## Coding Rules
- Do not hold positions overnight — all trades must exit by 15:45 ET
- Indicators (EMA, RSI) must be computed on the full dataset, not reset per day
- SL/TP must use absolute points (not price percentages)
- SL/TP checks use bar high/low; if both hit in the same bar, take the SL (conservative)
- One trade per day — first valid signal only
- Entry is on the open of the bar after the signal bar

## Known Pitfalls (do not repeat these mistakes)
- **Price-% stops are too wide for intraday NQ.** 2% of price = ~420 pts, larger than
  the entire daily range (~150-250 pts). Always use absolute point-based stops.
- **Resetting indicators per day causes cold-start bias.** EMA and RSI need prior
  session history to be meaningful. Always compute on the full dataset first.
- **Windows cp1252 encoding.** Avoid Unicode characters (arrows →, box-drawing ═─)
  in print statements — use plain ASCII (->  =  -) instead.
- **Modifying loop variable `i` inside a for loop has no effect in Python.** Use
  a while loop or index manually if you need to skip iterations.

## Position Sizing Logic
```
risk_per_contract = SL_POINTS * MULTIPLIER      # 60 * $2 = $120
contracts         = floor(MAX_RISK_DOLLARS / risk_per_contract)  # floor(500/120) = 4
```
Max loss per trade is capped at $500 regardless of equity size.

## After Every Backtest Iteration
1. Update this CLAUDE.md file with any new learnings, pitfalls, or parameter changes
   discovered in the session.
2. Push all changed files to GitHub with a descriptive commit message:

```bash
git add .
git commit -m "brief description of changes"
git push origin main
```

Commit message examples:
- "Fix SL/TP from price-% to absolute points; add RSI filter"
- "Cap max risk per trade at $500"
- "Add backtest_v2 notebook with changelog"

## Root Cause Analysis Findings (root_cause_analysis_v2.ipynb)
Two improvement areas were researched against v2 trade data:

**#1 Volume Confirmation**
- Trades filtered by signal_vol_ratio = signal_bar_volume / session_average_volume
- High-volume breakouts (ratio >= 1.0) have a meaningfully higher win rate than low-volume ones
- Low-volume breakouts tend to reverse immediately after the signal bar
- Recommended fix: only enter when signal bar volume >= session average

**#4 Trailing Stop to Break-Even**
- max_favorable_excursion (MFE) tracks the max points a trade moved in your favour before exiting
- Some trades reached 60+ pts profit (1R) then reversed into a full stop-out
- Moving the stop to break-even (entry price) once 1R is hit would convert those losses to flat
- Recommended fix: once trade is 60 pts in profit, move SL to entry price

## GitHub
Repository: https://github.com/kunpark04/futures
