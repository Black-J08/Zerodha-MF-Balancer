"""Unit tests for Reporter.

Tests Markdown report generation and file output.
"""

import os

import pytest

from src.core.evaluation import EvaluationMode
from src.core.models import FundExclusion, LumpSumAllocation, SIPAllocation, STPTransfer, TransferPlan
from src.core.settings import Settings
from src.reporting import Reporter


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Create a test Settings with temp output dir."""
    monkeypatch.setenv("KITE_API_KEY", "test_key")
    monkeypatch.setenv("KITE_API_SECRET", "test_secret")
    monkeypatch.chdir(tmp_path)
    return Settings.from_env()


def _make_transfer_plan(mode=EvaluationMode.MASTER_FUND):
    """Create a sample TransferPlan for testing."""
    stp_transfers = [
        STPTransfer(
            source_fund="Master Debt Fund" if mode == EvaluationMode.MASTER_FUND else "Fund A",
            target_fund="Fund B",
            monthly_amount=2500.0,
            duration_months=12,
            total_amount=30000.0,
        ),
        STPTransfer(
            source_fund="Master Debt Fund" if mode == EvaluationMode.MASTER_FUND else "Fund A",
            target_fund="Fund C",
            monthly_amount=1666.67,
            duration_months=12,
            total_amount=20000.0,
        ),
    ]
    sip_allocations = [
        SIPAllocation(
            target_fund="Fund B",
            monthly_amount=1000.0,
            percentage_of_contribution=50.0,
        ),
        SIPAllocation(
            target_fund="Fund C",
            monthly_amount=1000.0,
            percentage_of_contribution=50.0,
        ),
    ]
    lump_sum_allocations = [
        LumpSumAllocation(
            target_fund="Fund B",
            amount=5000.0,
            percentage_of_total=50.0,
        ),
        LumpSumAllocation(
            target_fund="Fund C",
            amount=5000.0,
            percentage_of_total=50.0,
        ),
    ]
    return TransferPlan(
        stp_transfers=stp_transfers,
        stp_monthly_total=4166.67,
        stp_duration_months=12,
        sip_allocations=sip_allocations,
        sip_monthly_total=2000.0,
        lump_sum_allocations=lump_sum_allocations,
        lump_sum_total=10000.0,
        shortfall_warnings=[],
        total_portfolio_value=200000.0,
        threshold_used=200.0,
    )


class TestReporter:
    """Tests for Reporter class."""

    def test_generate_report_creates_file(self, config):
        """Test that generate_report creates a markdown file."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfer_plan = _make_transfer_plan(EvaluationMode.MASTER_FUND)

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            mode=EvaluationMode.MASTER_FUND,
        )

        assert os.path.exists(filepath)
        assert filepath.endswith(".md")

        with open(filepath) as f:
            content = f.read()

        assert "# Mutual Fund Rebalancing Report" in content
        assert "Executive Summary" in content
        assert "Portfolio Allocation Comparison" in content
        assert "Current Weight" in content
        assert "Optimal Weight" in content
        assert "Target Value" in content
        assert "Action" in content
        assert "Fund A" in content
        assert "Fund B" in content
        assert "Execution Strategy Options" in content
        assert "Option 1: STP" in content
        assert "Option 2: SIP" in content
        assert "Option 3: Lump Sum" in content

    def test_generate_report_with_stats(self, config):
        """Test report generation with current and optimized stats."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfer_plan = _make_transfer_plan(EvaluationMode.MASTER_FUND)
        current_stats = {
            "Expected Return": 0.10,
            "Volatility": 0.15,
            "Sharpe Ratio": 0.67,
            "Max Drawdown": -0.10,
            "Sortino Ratio": 0.80,
        }
        optimized_stats = {
            "Expected Return": 0.15,
            "Volatility": 0.12,
            "Sharpe Ratio": 1.25,
            "Max Drawdown": -0.08,
            "Sortino Ratio": 1.50,
        }

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
            mode=EvaluationMode.MASTER_FUND,
        )

        with open(filepath) as f:
            content = f.read()

        assert "Portfolio Health Check" in content
        assert "Annual Return" in content
        assert "Sharpe Ratio" in content

    def test_generate_report_zero_transfers(self, config):
        """Test report with zero transfers."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 200000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 250000.0,
        }
        optimal_weights = {"Fund A": 0.8, "Fund B": 0.2}
        empty_transfer_plan = TransferPlan(
            stp_transfers=[],
            stp_monthly_total=0.0,
            stp_duration_months=12,
            sip_allocations=[],
            sip_monthly_total=0.0,
            lump_sum_allocations=[],
            lump_sum_total=0.0,
            shortfall_warnings=[],
            total_portfolio_value=250000.0,
            threshold_used=250.0,
        )

        filepath = reporter.generate_report(
            empty_transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            mode=EvaluationMode.MASTER_FUND,
        )

        with open(filepath) as f:
            content = f.read()

        assert "No transfers needed" in content

    def test_generate_report_mpt_optimal_labels(self, config):
        """Test MPT-Optimal mode uses Total Portfolio Capital labels."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 150000.0,
            "Total_Projected": 300000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfer_plan = _make_transfer_plan(EvaluationMode.MPT_OPTIMAL)

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            mode=EvaluationMode.MPT_OPTIMAL,
        )

        with open(filepath) as f:
            content = f.read()

        assert "Total Portfolio Capital" in content
        assert "Total Portfolio" in content
        assert "Debt Capital Source" not in content
        assert "Master Debt Fund" not in content

    def test_generate_report_shows_current_vs_optimal_allocation(self, config):
        """Report includes a current-vs-optimal allocation comparison table."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        current_weights = {"Fund A": 0.5, "Fund B": 0.5}
        transfer_plan = _make_transfer_plan(EvaluationMode.MASTER_FUND)

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            current_weights=current_weights,
            mode=EvaluationMode.MASTER_FUND,
        )

        with open(filepath) as f:
            content = f.read()

        assert "Portfolio Allocation Comparison" in content
        assert "Current Weight" in content
        assert "Optimal Weight" in content
        assert "Difference" in content
        assert "Current Value" in content
        assert "Target Value" in content
        assert "Action" in content

    def test_generate_report_shows_three_execution_strategies(self, config):
        """Report includes three execution strategies ordered by recommendation."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfer_plan = _make_transfer_plan(EvaluationMode.MASTER_FUND)

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            mode=EvaluationMode.MASTER_FUND,
        )

        with open(filepath) as f:
            content = f.read()

        assert "Execution Strategy Options" in content
        # STP first (Recommended)
        stp_pos = content.find("Option 1: STP")
        sip_pos = content.find("Option 2: SIP")
        lump_pos = content.find("Option 3: Lump Sum")
        assert stp_pos != -1
        assert sip_pos != -1
        assert lump_pos != -1
        assert stp_pos < sip_pos < lump_pos
        assert "Recommended" in content[stp_pos:sip_pos]
        assert "Least Recommended" in content[lump_pos:]

    def test_generate_report_includes_zero_weight_excluded_funds(self, config):
        """Report's Excluded Funds section lists zero-weight funds with reason."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Total_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        current_weights = {"Fund A": 0.5, "Fund B": 0.5, "Fund C": 0.0}
        transfer_plan = _make_transfer_plan(EvaluationMode.MASTER_FUND)
        excluded_funds = [
            FundExclusion(
                fund_name="Fund C",
                reason="Zero optimal weight",
                detail="Receives 0% allocation in the optimized portfolio; not included in target allocation",
            )
        ]

        filepath = reporter.generate_report(
            transfer_plan,
            allocator_summary,
            optimal_weights,
            duration=12,
            current_weights=current_weights,
            excluded_funds=excluded_funds,
            mode=EvaluationMode.MASTER_FUND,
        )

        with open(filepath) as f:
            content = f.read()

        assert "Excluded Funds" in content
        assert "Fund C" in content
        assert "Zero optimal weight" in content
