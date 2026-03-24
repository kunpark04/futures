"""
import_barchart.py
Cleans Barchart 5-min NQ CSV exports and merges them into data/NQ_5m.csv.

Barchart quirks handled:
  - 'Latest' column renamed to 'close'
  - 'Change' and '%Change' columns dropped
  - Footer line "Downloaded from Barchart.com..." stripped
  - Timestamps are Central Time (America/Chicago) -> converted to Eastern Time
  - Pre/post market bars filtered out (keep 09:30-16:00 ET only)
"""

import os
import glob
import pandas as pd

_ROOT         = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE    = os.path.join(_ROOT, "data", "NQ_5m.csv")
SESSION_START = pd.Timestamp("09:30", tz="America/New_York").time()
SESSION_END   = pd.Timestamp("16:00", tz="America/New_York").time()

BARCHART_FILES = sorted(glob.glob("nq*_intraday-5min_historical-data*.csv"))


def load_barchart(path: str) -> pd.DataFrame:
    """Load and clean a single Barchart CSV export."""
    # Read all lines, drop the Barchart footer row
    with open(path, "r") as f:
        lines = [l for l in f if not l.startswith('"Downloaded')]

    from io import StringIO
    df = pd.read_csv(StringIO("".join(lines)))

    if df.empty:
        return pd.DataFrame()

    # Rename columns to match yfinance format
    df = df.rename(columns={
        "Time":    "datetime",
        "Open":    "open",
        "High":    "high",
        "Low":     "low",
        "Latest":  "close",
        "Volume":  "volume",
    })

    # Drop Barchart-specific columns
    df = df.drop(columns=["Change", "%Change"], errors="ignore")

    # Parse timestamps as Central Time, convert to Eastern Time
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["datetime"] = df["datetime"].dt.tz_localize("America/Chicago").dt.tz_convert("America/New_York")
    df = df.set_index("datetime")

    # Filter to RTH session only: 09:30 - 16:00 ET
    mask = (df.index.time >= SESSION_START) & (df.index.time < SESSION_END)
    df = df[mask].copy()

    # Keep only OHLCV, drop any NaN rows
    df = df[["open", "high", "low", "close", "volume"]]
    df = df.dropna(subset=["open", "high", "low", "close"])

    return df


def load_existing_cache() -> pd.DataFrame:
    """Load the existing yfinance cache if it exists."""
    if not os.path.isfile(CACHE_FILE):
        return pd.DataFrame()
    df = pd.read_csv(CACHE_FILE, index_col="datetime")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
    return df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
print(f"Found {len(BARCHART_FILES)} Barchart file(s): {BARCHART_FILES}")

frames = []
for path in BARCHART_FILES:
    df = load_barchart(path)
    if df.empty:
        print(f"  Skipped (empty): {path}")
        continue
    print(f"  Loaded {len(df):,} rows  "
          f"({df.index[0].date()} -> {df.index[-1].date()})  {path}")
    frames.append(df)

existing = load_existing_cache()
if not existing.empty:
    print(f"  Loaded {len(existing):,} rows from existing cache "
          f"({existing.index[0].date()} -> {existing.index[-1].date()})")
    frames.append(existing)

if not frames:
    print("No data found. Exiting.")
    exit(1)

combined = pd.concat(frames)
combined = combined[~combined.index.duplicated(keep="last")]
combined = combined.sort_index()

os.makedirs("data", exist_ok=True)
combined.to_csv(CACHE_FILE)
print(f"\nSaved {len(combined):,} rows to {CACHE_FILE} "
      f"({combined.index[0].date()} -> {combined.index[-1].date()})")
