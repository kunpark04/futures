"""
data_fetch.py
Fetches NQ=F 5-minute OHLCV data from Yahoo Finance using yfinance.
"""

import os

import yfinance as yf
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TICKER     = "NQ=F"
INTERVAL   = "5m"
PERIOD     = "60d"   # yfinance max for 5-min data
_ROOT      = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(_ROOT, "data")
CACHE_FILE = os.path.join(CACHE_DIR, "NQ_5m.csv")

SESSION_START = pd.Timestamp("09:30", tz="America/New_York").time()
SESSION_END   = pd.Timestamp("16:00", tz="America/New_York").time()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_data(refresh: bool = False) -> pd.DataFrame:
    """
    Return a DataFrame of NQ=F 5-minute bars (last 60 calendar days).

    Parameters
    ----------
    refresh : bool
        If True, ignore the local cache and re-download via yfinance.

    Returns
    -------
    pd.DataFrame
        Columns: open, high, low, close, volume
        Index  : datetime (timezone-aware, US/Eastern)
    """
    if not refresh and os.path.isfile(CACHE_FILE):
        print(f"[data_fetch] Loading cached data from {CACHE_FILE} ...")
        df = pd.read_csv(CACHE_FILE, index_col="datetime")
        df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
        print(f"[data_fetch] Loaded {len(df):,} rows "
              f"({df.index[0].date()} -> {df.index[-1].date()})")
        return df

    print(f"[data_fetch] Downloading {TICKER} {INTERVAL} via yfinance ...")
    raw = yf.download(
        TICKER,
        period=PERIOD,
        interval=INTERVAL,
        auto_adjust=True,
        progress=False,
    )

    if raw.empty:
        raise RuntimeError(
            "yfinance returned no data for NQ=F. "
            "Check your internet connection or try again later."
        )

    # yfinance returns capitalized columns; normalise to lowercase
    raw.columns = [c[0].lower() if isinstance(c, tuple) else c.lower()
                   for c in raw.columns]
    raw.index.name = "datetime"

    # Ensure US/Eastern timezone
    if raw.index.tz is None:
        raw.index = raw.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        raw.index = raw.index.tz_convert("America/New_York")

    # Drop rows with any NaN in OHLC
    raw.dropna(subset=["open", "high", "low", "close"], inplace=True)

    # Keep only regular session bars: 09:30 - 16:00 ET
    mask = (raw.index.time >= SESSION_START) & (raw.index.time < SESSION_END)
    df = raw[mask].copy()

    df.sort_index(inplace=True)

    # Cache to disk
    os.makedirs(CACHE_DIR, exist_ok=True)
    df.to_csv(CACHE_FILE)
    print(f"[data_fetch] Saved {len(df):,} rows to {CACHE_FILE} "
          f"({df.index[0].date()} -> {df.index[-1].date()})")
    return df


if __name__ == "__main__":
    data = fetch_data(refresh=True)
    print(data.tail())
