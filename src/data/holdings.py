"""Portfolio holdings access from Zerodha Kite Connect.

Provides functions to fetch current mutual fund holdings from Zerodha
and normalize them into a standard DataFrame format.
"""

import pandas as pd
from kiteconnect import KiteConnect


def get_portfolio_holdings(kite: KiteConnect) -> pd.DataFrame:
    """Fetch current mutual fund holdings from Zerodha.

    Args:
        kite: Initialized :class:`kiteconnect.KiteConnect` instance with
            an access token set.

    Returns:
        A :class:`pandas.DataFrame` with columns:
        ``tradingsymbol``, ``isin``, ``quantity``, ``last_price``,
        ``average_price``, ``value``. Empty DataFrame if no holdings
        or on error.
    """
    try:
        holdings = kite.mf_holdings()
    except Exception:  # noqa: BLE001 - API failures must return empty DataFrame
        return pd.DataFrame()

    mf_holdings = []
    for h in holdings:
        # In MF response, tradingsymbol is often the ISIN
        mf_holdings.append(
            {
                "tradingsymbol": h.get("fund", h["tradingsymbol"]),
                "isin": h["tradingsymbol"],
                "quantity": h["quantity"],
                "last_price": h["last_price"],
                "average_price": h["average_price"],
                "value": h["quantity"] * h["last_price"],
            }
        )

    return pd.DataFrame(mf_holdings)
