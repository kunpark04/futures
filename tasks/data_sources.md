# NQ Futures Data Sources

## Current: Barchart (Manual CSV) — In Use
- 5-min NQ bars, ~10 years of history per contract via manual download
- Free with account (limited downloads/day on free tier)
- Settings: 5-min, volume checked, open interest unchecked, no dividend adjustment
- URL pattern: `barchart.com/futures/quotes/NQ{month}{year}/historical-download`
  - Month codes: H=Mar, M=Jun, U=Sep, Z=Dec (e.g. NQZ25 = Dec 2025 contract)
- Import script: `import_barchart.py` — drop CSVs in project root and re-run to extend dataset
- Raw files archived: `data/raw_data.zip` (47 contracts, NQH15-NQH26)

## Databento — Best Programmatic Alternative
- Dataset: `GLBX.MDP3` (CME Globex), covers NQ and MNQ
- History: 2010-present (~15 years)
- Cost: $125 free credit one-time; ~$0.50/GB pay-as-you-go after
- No native 5-min schema — download 1-min bars and resample with pandas
- Python SDK: `pip install databento`
- Worth integrating when automating the data refresh pipeline

## Interactive Brokers — Cannot Use
- User confirmed they cannot use Interactive Brokers.

## Alpaca — No Futures Yet
- Stocks and crypto only. Futures on roadmap. Check back.
- Python SDK: `pip install alpaca-py`

## TradingView Charting Library — Deferred
- Visualization only, ships with no data
- Revisit when building a public-facing web dashboard
- Not relevant for current notebook/CLI workflow

## Others Researched and Rejected
- **Norgate:** Daily bars only, no intraday
- **Tradovate:** $400+/month CME license required — prohibitive
- **Stooq/Investing.com:** Intraday broken or daily only for futures
- **Polygon/Massive:** Futures not yet launched (beta)
- **FirstRate Data:** ~$300 one-time for 18yr NQ CSVs — viable if Barchart becomes insufficient
