"""Unit tests for Reporter.

Tests Markdown report generation and file output.
"""

import os

import pytest

from src.core.settings import Settings
from src.reporting import Reporter


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Create a test Settings with temp output dir."""
    monkeypatch.setenv("KITE_API_KEY", "test_key")
    monkeypatch.setenv("KITE_API_SECRET", "test_secret")
    monkeypatch.chdir(tmp_path)
    return Settings.from_env()


class TestReporter:
    """Tests for Reporter class."""

    def test_generate_report_creates_file(self, config):
        """Test that generate_report creates a markdown file."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Debt_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfers = {"Fund A": 2500.0, "Fund B": 1666.67}

        filepath = reporter.generate_report(
            allocator_summary, optimal_weights, transfers, duration=12
        )

        assert os.path.exists(filepath)
        assert filepath.endswith(".md")

        with open(filepath) as f:
            content = f.read()

        assert "# Mutual Fund Rebalancing Report" in content
        assert "Executive Summary" in content
        assert "Optimal Allocation (MPT)" in content
        assert "Fund A" in content
        assert "Fund B" in content
        assert "Monthly STP Plan" in content

    def test_generate_report_with_stats(self, config):
        """Test report generation with current and optimized stats."""
        reporter = Reporter(config)

        allocator_summary = {
            "Total_Equity": 150000.0,
            "Debt_Capital": 50000.0,
            "Total_Projected": 200000.0,
        }
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        transfers = {"Fund A": 2500.0}
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
            allocator_summary,
            optimal_weights,
            transfers,
            duration=12,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
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
            "Debt_Capital": 50000.0,
            "Total_Projected": 250000.0,
        }
        optimal_weights = {"Fund A": 0.8, "Fund B": 0.2}
        transfers = {"Fund A": 0.0, "Fund B": 0.0}

        filepath = reporter.generate_report(
            allocator_summary, optimal_weights, transfers, duration=12
        )

        with open(filepath) as f:
            content = f.read()

        assert "No transfers needed" in content
