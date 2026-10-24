"""Unit tests for Allocator.

Tests STP transfer amount calculation, shortfall logic,
and edge cases.
"""

from src.allocation import Allocator


class TestAllocator:
    """Tests for Allocator class."""

    def test_calculate_transfers_basic(self):
        """Test basic transfer calculation."""
        current_holdings = {"Fund A": 100000.0, "Fund B": 50000.0}
        debt_capital = 50000.0
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}
        remaining_months = 12

        allocator = Allocator(
            current_holdings, debt_capital, optimal_weights, remaining_months
        )
        transfers = allocator.calculate_transfers()

        assert isinstance(transfers, dict)
        assert set(transfers.keys()) == {"Fund A", "Fund B"}
        # Total monthly outflow should equal debt_capital / months
        total = sum(transfers.values())
        assert abs(total - (debt_capital / remaining_months)) < 0.01

    def test_calculate_transfers_with_shortfall(self):
        """Test that funds with shortfall get proportional allocation."""
        current_holdings = {"Fund A": 100000.0, "Fund B": 10000.0}
        debt_capital = 120000.0
        optimal_weights = {"Fund A": 0.5, "Fund B": 0.5}
        remaining_months = 12

        allocator = Allocator(
            current_holdings, debt_capital, optimal_weights, remaining_months
        )
        transfers = allocator.calculate_transfers()

        # Fund B has a larger shortfall (target 60000 - current 10000 = 50000)
        # Fund A has smaller shortfall (target 60000 - current 100000 = -40000, so 0)
        # So Fund B should get most/all of the budget
        assert transfers["Fund B"] > transfers["Fund A"]

    def test_calculate_transfers_all_overweight(self):
        """Test edge case where all funds are overweight."""
        current_holdings = {"Fund A": 200000.0, "Fund B": 200000.0}
        debt_capital = 10000.0
        optimal_weights = {"Fund A": 0.5, "Fund B": 0.5}
        remaining_months = 12

        allocator = Allocator(
            current_holdings, debt_capital, optimal_weights, remaining_months
        )
        transfers = allocator.calculate_transfers()

        # All overweight -> fallback to optimal weights * monthly_budget
        monthly_budget = debt_capital / remaining_months
        assert abs(transfers["Fund A"] - (0.5 * monthly_budget)) < 0.01
        assert abs(transfers["Fund B"] - (0.5 * monthly_budget)) < 0.01

    def test_get_summary(self):
        """Test get_summary returns correct values."""
        current_holdings = {"Fund A": 100000.0, "Fund B": 50000.0}
        debt_capital = 50000.0
        optimal_weights = {"Fund A": 0.6, "Fund B": 0.4}

        allocator = Allocator(
            current_holdings, debt_capital, optimal_weights, 12
        )
        summary = allocator.get_summary()

        assert summary["Total_Equity"] == 150000.0
        assert summary["Debt_Capital"] == 50000.0
        assert summary["Total_Projected"] == 200000.0

    def test_remaining_months_min_one(self):
        """Test that remaining_months is at least 1."""
        allocator = Allocator(
            {"Fund A": 100000.0}, 10000.0, {"Fund A": 1.0}, 0
        )
        assert allocator.remaining_months == 1
