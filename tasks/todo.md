# Todo — Futures_v2

## Pending Implementation

- [ ] **Implement trailing stop to break-even (RCA #4)**
  - Once a trade is 60 pts in profit (1R), move SL from original stop to entry price
  - Expected improvement: +$960 across 2 affected trades in v2 dataset
  - Update strategy.py and create backtest_v3.ipynb with changelog
  - After implementing: update CLAUDE.md, tasks/lessons.md, and push to GitHub

## Next Session

- [ ] **Run full dataset backtest** — dataset now covers Dec 2014 - Mar 2026 (~11.3 years, 222,295 bars) vs the previous 60-day yfinance window. Re-run ORB + EMA-20 + RSI-14 strategy and check performance targets (win rate >= 50%, Sharpe > 1.0)
- [ ] **Implement trailing stop to break-even** (carry over from Pending above) before or alongside the full backtest
- [ ] **Integrate VectorBT** — replace loop-based backtester in strategy.py with vectorized engine for speed and parameter sweeps (SL/TP/RSI combinations). Install: `pip install vectorbt`
- [ ] **Integrate Pyfolio** — replace manual analysis.py metrics with professional tear sheets (rolling Sharpe, monthly heatmap, drawdown table). Install: `pip install pyfolio`
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
