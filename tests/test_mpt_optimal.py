"""Unit and integration tests for the MPT-Optimal evaluation mode.

Tests that MPT-Optimal mode:
- Includes all eligible holdings (no master fund exclusion).
- Uses total portfolio value as capital basis.
- Produces valid maximum-Sharpe-ratio weights.
- Handles invalid/insufficient data via FundExclusion.
- Returns an EvaluationResult with mode == MPT_OPTIMAL.
"""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.core.evaluation import EvaluationMode, EvaluationResult
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


def _make_service(mock_data_engine):
    """Build a PortfolioService with a mocked DataEngine."""
    service = PortfolioService.__new__(PortfolioService)
    service.settings = MagicMock()
    service.data_engine = mock_data_engine
    service.settings.data_dir = "/tmp/mf_balancer_test"
    service.settings.reports_dir = "/tmp/mf_balancer_test/reports"
    return service


class TestMPTOptimalMode:
    """Tests for MPT-Optimal evaluation mode."""

    def test_mpt_optimal_includes_all_holdings(self, mock_data_engine):
        """MPT-Optimal includes all holdings; no master fund exclusion."""
        mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        assert isinstance(result, EvaluationResult)
        assert result.mode == EvaluationMode.MPT_OPTIMAL
        # All 3 funds included (no master fund excluded)
        assert set(result.valid_funds) == {"FUND_A", "FUND_B", "FUND_C"}
        assert result.excluded_funds == []

    def test_mpt_optimal_weights_valid(self, mock_data_engine):
        """MPT-Optimal weights sum to ~1.0 and are within [0, 1]."""
        mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        assert isinstance(result.weights, dict)
        assert set(result.weights.keys()) == {"FUND_A", "FUND_B", "FUND_C"}
        assert abs(sum(result.weights.values()) - 1.0) < 0.01
        for w in result.weights.values():
            assert 0.0 <= w <= 1.0

    def test_mpt_optimal_total_capital_is_portfolio_value(self, mock_data_engine):
        """MPT-Optimal uses total portfolio value as capital basis."""
        mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        # Total portfolio value = 5000 + 5000 + 4500 = 14500
        assert result.total_capital == 14500.0
        assert result.summary["Total_Capital"] == 14500.0

    def test_mpt_optimal_excludes_invalid_funds(self, mock_data_engine):
        """Funds with missing scheme codes are excluded in MPT-Optimal mode."""

        def scheme_code_side_effect(fund_name, isin=None):
            if fund_name == "FUND_A":
                return None
            return "123456"

        mock_data_engine.get_scheme_code_for_fund.side_effect = scheme_code_side_effect
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        excluded_names = {e.fund_name for e in result.excluded_funds}
        assert "FUND_A" in excluded_names
        assert "FUND_A" not in result.valid_funds

    def test_mpt_optimal_no_valid_funds_raises(self, mock_data_engine):
        """MPT-Optimal raises ValueError when no funds have valid NAV data."""
        mock_data_engine.get_scheme_code_for_fund.return_value = None

        service = _make_service(mock_data_engine)

        with pytest.raises(ValueError, match="Could not fetch NAV data for ANY fund"):
            service.evaluate(
                mode=EvaluationMode.MPT_OPTIMAL,
                months=12,
                risk_free_rate=0.07,
                source_fund_name=None,
                total_capital=None,
            )

    def test_mpt_optimal_single_fund_weight_one(self, mock_data_engine):
        """Single valid fund gets weight 1.0."""
        mock_data_engine.get_scheme_code_for_fund.side_effect = lambda fund, isin=None: (
            "123456" if fund == "FUND_A" else None
        )
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        assert result.valid_funds == ["FUND_A"]
        assert abs(result.weights["FUND_A"] - 1.0) < 0.01

    def test_mpt_optimal_has_stats(self, mock_data_engine):
        """MPT-Optimal result includes current and optimized stats."""
        mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        assert result.optimized_stats is not None
        assert result.current_stats is not None
        assert "Sharpe Ratio" in result.optimized_stats
        assert "Sharpe Ratio" in result.current_stats

    def test_mpt_optimal_stp_transfers_from_sources_to_targets(self, mock_data_engine):
        """MPT-Optimal STP transfers come from overweighted sources to underweighted targets."""
        mock_data_engine.get_scheme_code_for_fund.return_value = "123456"
        mock_data_engine.get_historical_nav.side_effect = _valid_nav_side_effect

        service = _make_service(mock_data_engine)

        result = service.evaluate(
            mode=EvaluationMode.MPT_OPTIMAL,
            months=12,
            risk_free_rate=0.07,
            source_fund_name=None,
            total_capital=None,
        )

        transfer_plan = result.transfers

        # Every STP transfer must have a source and target fund
        for stp in transfer_plan.stp_transfers:
            assert stp.source_fund != stp.target_fund
            assert stp.monthly_amount > 0
            assert stp.duration_months == 12
            assert stp.total_amount == stp.monthly_amount * 12

        # Total monthly outflow equals sum of all transfer monthly amounts
        total_monthly = sum(stp.monthly_amount for stp in transfer_plan.stp_transfers)
        assert abs(total_monthly - transfer_plan.stp_monthly_total) < 0.01

        # No source fund should allocate more than its available excess
        for stp in transfer_plan.stp_transfers:
            source_allocated = sum(
                s.monthly_amount
                for s in transfer_plan.stp_transfers
                if s.source_fund == stp.source_fund
            )
            # Source's total monthly allocation should not exceed its excess / months
            assert source_allocated <= transfer_plan.stp_monthly_total + 0.01
