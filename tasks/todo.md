# Todo — Futures_v2

## Pending Implementation

- [ ] **Implement trailing stop to break-even (RCA #4)**
  - Once a trade is 60 pts in profit (1R), move SL from original stop to entry price
  - Expected improvement: +$960 across 2 affected trades in v2 dataset
  - Update strategy.py and create backtest_v3.ipynb with changelog
  - After implementing: update CLAUDE.md, tasks/lessons.md, and push to GitHub

## Potential Future Improvements (not yet researched)

- [ ] ATR-based dynamic stop distance instead of fixed 60 pts
- [ ] Time-of-day filter (e.g. avoid entries after 14:00 ET)
- [ ] Multi-day session analysis (Monday vs Friday performance)
- [ ] Extend backtest data beyond 60-day yfinance limit

## Completed

- [x] Fix SL/TP from price-% to absolute points (60/120 pts)
- [x] Add RSI-14 confirmation filter (>52 long, <48 short)
- [x] Move EMA/RSI computation to full dataset (eliminate cold-start bias)
- [x] Switch data source from urllib+json to yfinance
- [x] Cap max risk per trade at $500
- [x] Create root_cause_analysis_v2.ipynb (volume filter + trailing stop)
- [x] Push all files to GitHub (kunpark04/futures)
