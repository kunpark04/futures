# Lessons Learned — Futures_v2

## Strategy & Backtesting

**Price-% stops are too wide for intraday NQ**
- 2% of NQ price (~21,000) = 420 pts stop, 4% = 840 pts TP
- NQ's average daily range is only 150-250 pts — neither level ever triggered intraday
- Every trade exited at EOD, masking true signal quality
- Fix: always use absolute point-based stops (SL=60pts, TP=120pts)

**Resetting indicators per day causes cold-start bias**
- EMA-20 and RSI-14 computed fresh each day start from cold with no history
- RSI takes 14+ bars to converge; first ORB signal fires around bar 6-15
- RSI was still warming up when signals fired — filter had zero effect (same 47 trades)
- Fix: compute EMA and RSI on the full dataset before the daily backtest loop

**Volume filter hypothesis was wrong**
- Expected: high-volume breakouts outperform low-volume ones
- Actual: low-volume trades had 88.9% win rate and $4,442 P&L — the best trades
- Filtering by volume >= session average would have removed the most profitable trades
- Lesson: always verify assumptions with data before implementing a filter

**Trailing stop improves risk-adjusted returns but does not create wins**
- Trailing stop to break-even converts losses to flat ($0), not wins
- Only 2 trades out of 46 were affected (+$960 improvement)
- Lesson: clarify the mechanism of any improvement before reporting it

## Workflow

**Always enter plan mode before writing any code**
- User explicitly requires plan mode before any coding, not just non-trivial tasks
- Skipping plan mode (even for small changes) will be caught and flagged

**Relative data paths break when Jupyter sets a different CWD**
- `data_fetch.py` used `"data/NQ_5m.csv"` (relative to CWD)
- Notebooks in `notebooks/original/` set CWD to that directory, so `data/NQ_5m.csv`
  resolved to `notebooks/original/data/NQ_5m.csv` — a stale 3,700-row yfinance copy
- Fix: use `os.path.dirname(os.path.abspath(__file__))` in any module that accesses
  the data file, so the path is always relative to the module, not the caller's CWD

## Python / Technical

**Modifying `i` inside a for loop has no effect**
- `i += 1` inside `for i, bar in enumerate(bars)` does nothing — Python recalculates `i` each iteration
- Fix: use a while loop with manual index management if skipping iterations is needed

**yfinance CSV cache reload drops timezone**
- `pd.read_csv()` + `pd.to_datetime(df.index)` returns tz-naive index
- Session time filtering (09:30-16:00 ET) silently breaks — all bars pass or all fail
- Fix: `df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")`

**Windows cp1252 encoding crashes on Unicode**
- Unicode arrows (->), box-drawing chars, and warning symbols cause UnicodeEncodeError on Windows
- Fix: use plain ASCII only in all print statements and file writes
