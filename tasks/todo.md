# Todo — Futures_v2

## Pending Implementation

- [x] **Implement trailing stop to break-even (RCA #4)**
  - Implemented as `trailing_stop_be=True/False` parameter on `run_backtest()`
  - Default set to False — full 11yr test shows BE hurts: -$30k, win rate 44.7% -> 38.8%
  - Documented in backtest_v3.ipynb; CLAUDE.md updated with finding

## Next Session

- [x] **Run full dataset backtest** — 2,740 trades over 11.3 years; win rate 44.7% (below 50% target); see backtest_v3.ipynb
- [x] **Integrate VectorBT** — `vectorbt_integration.ipynb` compares loop vs VectorBT on 222k bars; 27x speedup. 2 irreconcilable differences documented: -9 trades (early-close days skipped by VBT) + ~$7.5k P&L gap (same-bar SL/TP resolution). Ready for parameter sweeps.
- [x] **Integrate Pyfolio** — added `pyfolio_tearsheet()` to analysis.py; saves output/tearsheet.pdf with alpha/beta vs intraday NQ benchmark, rolling Sharpe, drawdown table. Uses pyfolio-reloaded (pip install pyfolio-reloaded)
- [ ] **Backtrader** — defer until live trading; needed for IB connector and StopTrail order type

## Data Pipeline (completed this session)

- [x] Replace yfinance (60-day cap) with Barchart CSV imports via import_barchart.py
- [x] Built dataset: Dec 2014 - Mar 2026, 222,295 rows, 47 contracts (NQH15-NQH26)
- [x] Raw files archived to data/raw_data.zip; cleaned data in data/NQ_5m.csv
- [x] To extend dataset: download new contract CSVs from barchart.com, drop in project root, re-run import_barchart.py
- [x] Barchart URL pattern: barchart.com/futures/quotes/NQ{month}{year}/historical-download

## Potential Future Improvements (not yet researched)

- [ ] ATR-based dynamic stop distance instead of fixed 60 pts
- [ ] Time-of-day filter (e.g. avoid entries after 14:00 ET)
- [ ] Multi-day session analysis (Monday vs Friday performance)

## Completed

- [x] Fix SL/TP from price-% to absolute points (60/120 pts)
- [x] Add RSI-14 confirmation filter (>52 long, <48 short)
- [x] Move EMA/RSI computation to full dataset (eliminate cold-start bias)
- [x] Switch data source from urllib+json to yfinance
- [x] Cap max risk per trade at $500
- [x] Create root_cause_analysis_v2.ipynb (volume filter + trailing stop)
- [x] Push all files to GitHub (kunpark04/futures)
