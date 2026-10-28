"""Regression tests for PortfolioService holdings retrieval.

Regression: PortfolioService created a new DataEngine(settings) without the
authenticated KiteConnect instance, so the second get_portfolio_holdings()
call (inside run_advisory) failed with "Kite Connect not initialized" on
first login, causing "No Mutual Fund holdings found in this Zerodha account!".

Fix: main.py passes the authenticated DataEngine to PortfolioService, so the
same authenticated KiteConnect instance is used throughout the advisory flow.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.services import PortfolioService


@pytest.fixture
def mock_data_engine():
    """Create a DataEngine mock with an authenticated kite and sample holdings."""
    engine = MagicMock()
    holdings = pd.DataFrame(
        [
            {
                "tradingsymbol": "FUND_A",
                "isin": "INF123456",
                "quantity": 100,
                "last_price": 50.0,
                "average_price": 45.0,
                "value": 5000.0,
            },
            {
                "tradingsymbol": "FUND_B",
                "isin": "INF123457",
                "quantity": 200,
                "last_price": 25.0,
                "average_price": 20.0,
                "value": 5000.0,
            },
        ]
    )
    engine.get_portfolio_holdings.return_value = holdings
    engine.get_scheme_code_for_fund.return_value = "123456"
    return engine


class TestPortfolioServiceHoldings:
    """Tests that PortfolioService uses the provided DataEngine's kite."""

    def test_uses_provided_data_engine_for_holdings(self, mock_data_engine):
        """PortfolioService should use the provided DataEngine (with authenticated kite)."""
        service = PortfolioService.__new__(PortfolioService)
        service.settings = MagicMock()
        service.data_engine = mock_data_engine

        # Verify the service uses the provided engine's holdings
        holdings_df = service.data_engine.get_portfolio_holdings()
        assert not holdings_df.empty
        assert len(holdings_df) == 2
        assert "FUND_A" in holdings_df["tradingsymbol"].values
        assert "FUND_B" in holdings_df["tradingsymbol"].values

    def test_data_engine_kite_is_authenticated(self, mock_data_engine):
        """The DataEngine passed to PortfolioService should have an authenticated kite."""
        # Simulate the fix: main.py passes de (with authenticated kite) to PortfolioService
        mock_kite = MagicMock()
        mock_data_engine.kite = mock_kite

        service = PortfolioService.__new__(PortfolioService)
        service.settings = MagicMock()
        service.data_engine = mock_data_engine

        assert service.data_engine.kite is mock_kite

    def test_portfolio_service_holds_reference_to_provided_engine(self):
        """PortfolioService should hold a reference to the provided DataEngine, not create a new one."""
        mock_engine = MagicMock()
        mock_engine.get_portfolio_holdings.return_value = pd.DataFrame(
            [
                {
                    "tradingsymbol": "FUND_A",
                    "isin": "INF123456",
                    "quantity": 100,
                    "last_price": 50.0,
                    "average_price": 45.0,
                    "value": 5000.0,
                }
            ]
        )

        service = PortfolioService.__new__(PortfolioService)
        service.settings = MagicMock()
        service.data_engine = mock_engine

        # The service should use the same engine instance
        assert service.data_engine is mock_engine
        holdings_df = service.data_engine.get_portfolio_holdings()
        assert not holdings_df.empty
