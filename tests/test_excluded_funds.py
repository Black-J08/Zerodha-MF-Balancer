"""Unit tests for excluded-fund tracking in PortfolioService.

Verifies that each fund excluded during optimization is recorded as a
:class:`FundExclusion` with a reason and optional detail, and that valid
funds are never listed as excluded.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.services import PortfolioService


@pytest.fixture
def mock_data_engine():
    """Create a DataEngine mock with sample holdings and NAV behavior."""
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
            {
                "tradingsymbol": "FUND_C",
                "isin": "INF123458",
                "quantity": 150,
                "last_price": 30.0,
                "average_price": 28.0,
                "value": 4500.0,
            },
            {
                "tradingsymbol": "FUND_D",
                "isin": "INF123459",
                "quantity": 80,
                "last_price": 40.0,
                "average_price": 38.0,
                "value": 3200.0,
            },
            {
                "tradingsymbol": "FUND_E",
                "isin": "INF123460",
                "quantity": 60,
                "last_price": 55.0,
                "average_price": 50.0,
                "value": 3300.0,
            },
        ]
    )
    engine.get_portfolio_holdings.return_value = holdings
    return engine


def _make_nav_series(days: int) -> pd.Series:
    """Create a NAV series with the given number of days."""
    dates = pd.date_range("2023-01-01", periods=days, freq="D")
    return pd.Series(range(100, 100 + days), index=dates, dtype=float)


def _valid_nav_side_effect(code: str) -> pd.Series:
    """Return valid NAV data for any scheme code."""
    return _make_nav_series(100)


def test_exclusion_when_scheme_code_not_found(mock_data_engine):
    """Fund with no AMFI scheme code is excluded with reason 'Scheme code not found'."""

    def scheme_code_side_effect(fund_name, isin=None):
        if fund_name == "FUND_A":
            return None
        return "123456"

    mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
    mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert "FUND_A" in excluded_names
    scheme_code_exclusion = next(
        e for e in result.excluded_funds if e.fund_name == "FUND_A"
    )
    assert scheme_code_exclusion.reason == "Scheme code not found"
    assert scheme_code_exclusion.detail is None


def test_exclusion_when_no_nav_data(mock_data_engine):
    """Fund with empty NAV series is excluded with reason 'No NAV data returned'."""

    def scheme_code_side_effect(fund_name, isin=None):
        codes = {
            "FUND_A": "123456",
            "FUND_B": "123457",
            "FUND_C": "123458",
            "FUND_D": "123459",
            "FUND_E": "123460",
        }
        return codes[fund_name]

    def nav_side_effect(code):
        # Return empty series only for FUND_A's scheme code
        if code == "123456":
            return pd.Series(dtype=float)
        return _make_nav_series(100)

    mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
    mock_data_engine.get_historical_nav.side_effect = nav_side_effect

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert "FUND_A" in excluded_names
    no_data_exclusion = next(
        e for e in result.excluded_funds if e.fund_name == "FUND_A"
    )
    assert no_data_exclusion.reason == "No NAV data returned"
    assert no_data_exclusion.detail is None


def test_exclusion_when_insufficient_history(mock_data_engine):
    """Fund with <30 days of history is excluded with reason 'Insufficient history'."""

    def scheme_code_side_effect(fund_name, isin=None):
        codes = {
            "FUND_A": "123456",
            "FUND_B": "123457",
            "FUND_C": "123458",
            "FUND_D": "123459",
            "FUND_E": "123460",
        }
        return codes[fund_name]

    def nav_side_effect(code):
        # Return short series only for FUND_A's scheme code
        if code == "123456":
            return _make_nav_series(10)
        return _make_nav_series(100)

    mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
    mock_data_engine.get_historical_nav.side_effect = nav_side_effect

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert "FUND_A" in excluded_names
    hist_exclusion = next(
        e for e in result.excluded_funds if e.fund_name == "FUND_A"
    )
    assert hist_exclusion.reason == "Insufficient history"
    assert "10 days found, 30 required" in hist_exclusion.detail


def test_exclusion_when_nav_fetch_fails(mock_data_engine):
    """Fund whose NAV fetch raises is excluded with reason 'NAV fetch failed'."""

    def scheme_code_side_effect(fund_name, isin=None):
        codes = {
            "FUND_A": "123456",
            "FUND_B": "123457",
            "FUND_C": "123458",
            "FUND_D": "123459",
            "FUND_E": "123460",
        }
        return codes[fund_name]

    def nav_side_effect(code):
        if code == "123456":
            raise RuntimeError("network down")
        return _make_nav_series(100)

    mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
    mock_data_engine.get_historical_nav.side_effect = nav_side_effect

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert "FUND_A" in excluded_names
    fetch_exclusion = next(
        e for e in result.excluded_funds if e.fund_name == "FUND_A"
    )
    assert fetch_exclusion.reason == "NAV fetch failed"


def test_valid_funds_not_excluded(mock_data_engine):
    """Funds with valid NAV data are not listed as excluded."""
    mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
    mock_data_engine.get_historical_nav.return_value = _make_nav_series(100)

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert excluded_names == set()
    assert len(result.valid_funds) == 5


def test_no_fund_in_both_excluded_and_valid(mock_data_engine):
    """No fund appears in both excluded_funds and valid_funds."""
    # FUND_A has no scheme code (excluded), FUND_B has valid NAV (included)
    def scheme_code_side_effect(fund_name, isin=None):
        if fund_name == "FUND_A":
            return None
        return "123456"

    mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
    mock_data_engine.get_historical_nav.return_value = _make_nav_series(100)

    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"

    result = service.run_advisory(
        debt_capital=10000.0,
        months=12,
        risk_free_rate=0.07,
        source_fund_name=None,
    )

    excluded_names = {e.fund_name for e in result.excluded_funds}
    assert "FUND_A" in excluded_names
    assert "FUND_A" not in result.valid_funds
    assert set(result.valid_funds).isdisjoint(excluded_names)
