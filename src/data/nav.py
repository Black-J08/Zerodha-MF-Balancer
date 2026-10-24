"""Historical NAV data access.

Provides functions to fetch historical NAV data for mutual fund schemes
using mftool.
"""

from datetime import datetime, timedelta

import pandas as pd
from mftool import Mftool


def get_historical_nav(
    mftool: Mftool, scheme_code: str, years: int = 3
) -> pd.Series:
    """Fetch historical NAV for a given scheme code.

    Args:
        mftool: Initialized :class:`mftool.Mftool` instance.
        scheme_code: AMFI scheme code.
        years: Number of years of history to fetch (default 3).

    Returns:
        A :class:`pandas.Series` with dates as index and NAV values,
        sorted ascending by date.

    Raises:
        ValueError: If no data is returned for the scheme code.
    """
    data = mftool.get_scheme_historical_nav(scheme_code)

    if not data or "data" not in data:
        raise ValueError(f"Could not fetch data for scheme {scheme_code}")

    df = pd.DataFrame(data["data"])
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
    df["nav"] = pd.to_numeric(df["nav"])
    df = df.set_index("date").sort_index()

    # Filter for the requested period
    start_date = datetime.now() - timedelta(days=years * 365)
    df = df[df.index >= start_date]

    return df["nav"]
