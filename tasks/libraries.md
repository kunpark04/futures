# Python Finance Libraries

## VectorBT — High Priority
- **Role:** Replace loop-based backtester in strategy.py
- **Why:** Vectorized NumPy/Numba engine; tests thousands of SL/TP/RSI parameter combinations in seconds
- **Features:** Built-in EMA, RSI; Sharpe, win rate, drawdown out of the box; Plotly charts in Jupyter; yfinance + Alpaca connectors
- **Install:** `pip install vectorbt`
- **Key API:**
```python
pf = vbt.Portfolio.from_signals(price, entries, exits, init_cash=50000)
print(pf.stats())  # Sharpe, win rate, max drawdown, total return
```

## Pyfolio — Medium Priority
- **Role:** Replace manual metrics in analysis.py with professional tear sheets
- **Features:** Rolling Sharpe, monthly returns heatmap, drawdown table, benchmark comparison
- **Install:** `pip install pyfolio`
- **Key API:** `pf.create_full_tear_sheet(returns_series)`
- **Note:** Quantopian-era library, infrequent updates but still functional

## Backtrader — Deferred (live trading only)
- **Role:** Live trading migration path via Interactive Brokers connector
- **Features:** 122 built-in indicators; StopTrail order type (needed for trailing stop to break-even); CSV/pandas data feeds; commission/slippage models
- **Install:** `pip install backtrader`
- **Do not prioritise** until transitioning to live trading

## FinRL — Skip
- ML/reinforcement learning only. Not relevant to rules-based ORB strategy.

## FinQuant — Skip
- Multi-asset portfolio optimization. Not relevant for single-instrument strategy.

## Alpaca SDK — Watch list
- No futures data yet (on their roadmap). Check back periodically.
- Install: `pip install alpaca-py`
