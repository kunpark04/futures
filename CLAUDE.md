# Project Instructions

## After Every Backtest Iteration
After completing any backtest iteration (new notebook, strategy changes, parameter updates, bug fixes), always push the updated files to the GitHub repo with a commit message that briefly describes the changes made.

Example workflow:
```bash
git add .
git commit -m "brief description of changes made"
git push origin main
```

Commit message should summarize what changed, e.g.:
- "Fix SL/TP from price-% to absolute points; add RSI filter"
- "Cap max risk per trade at $500"
- "Add backtest_v2 notebook with changelog"
