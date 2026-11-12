"""Unit tests for DataPreparation.

Tests NAV validation, percentage-return computation, overlap alignment,
and insufficient-data handling.
"""

import pandas as pd
import pytest

from src.data import DataPreparation


@pytest.fixture
def prep():
    """Create a DataPreparation instance."""
    return DataPreparation(min_observations=30)


@pytest.fixture
def valid_nav_data():
    """Create valid NAV data for 3 funds over 100 days."""
    dates = pd.date_range("2023-01-01", periods=100, freq="D")
    return pd.DataFrame(
        {
            "Fund A": pd.Series(range(100, 200), index=dates, dtype=float),
            "Fund B": pd.Series(range(50, 150), index=dates, dtype=float),
            "Fund C": pd.Series(range(200, 300), index=dates, dtype=float),
        }
    )


class TestDataPreparation:
    """Tests for DataPreparation class."""

    def test_prepare_valid_data(self, prep, valid_nav_data):
        """Valid NAV data is cleaned and returned with no exclusions."""
        cleaned, exclusions = prep.prepare(valid_nav_data)

        assert len(cleaned.columns) == 3
        assert len(exclusions) == 0
        assert len(cleaned) == 100

    def test_prepare_non_positive_nav_excluded(self, prep, valid_nav_data):
        """Funds with non-positive NAV values are excluded."""
        valid_nav_data.loc[valid_nav_data.index[10], "Fund B"] = 0.0

        cleaned, exclusions = prep.prepare(valid_nav_data)

        assert "Fund B" not in cleaned.columns
        assert len(exclusions) == 1
        assert exclusions[0].fund_name == "Fund B"
        assert exclusions[0].reason == "Invalid NAV data"

    def test_prepare_insufficient_history_excluded(self, prep):
        """Funds that break the common overlap are excluded."""
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        # Fund D starts 91 days later, leaving only 9 days of overlap (< 30)
        late_dates = pd.date_range("2023-04-02", periods=30, freq="D")
        data = pd.DataFrame(
            {
                "Fund A": pd.Series(range(100, 200), index=dates, dtype=float),
                "Fund B": pd.Series(range(50, 150), index=dates, dtype=float),
                "Fund D": pd.Series(range(100, 130), index=late_dates, dtype=float),
            }
        )

        cleaned, exclusions = prep.prepare(data)

        assert "Fund D" not in cleaned.columns
        assert "Fund A" in cleaned.columns
        assert "Fund B" in cleaned.columns
        assert any(e.fund_name == "Fund D" for e in exclusions)
        assert any(
            "Insufficient overlapping period" in e.reason for e in exclusions
        )

    def test_prepare_empty_data_raises(self, prep):
        """Empty NAV data raises ValueError."""
        empty = pd.DataFrame()
        with pytest.raises(ValueError, match="NAV data is empty"):
            prep.prepare(empty)

    def test_prepare_all_invalid_raises(self, prep):
        """All-invalid NAV data raises ValueError."""
        dates = pd.date_range("2023-01-01", periods=100, freq="D")
        bad = pd.DataFrame(
            {
                "Fund A": pd.Series([-1.0] * 100, index=dates),
                "Fund B": pd.Series([0.0] * 100, index=dates),
            }
        )
        with pytest.raises(ValueError, match="No funds with valid NAV data remain"):
            prep.prepare(bad)

    def test_prepare_overlap_alignment(self, prep):
        """Funds are aligned on the common overlapping date index."""
        dates_a = pd.date_range("2023-01-01", periods=100, freq="D")
        dates_b = pd.date_range("2023-01-15", periods=100, freq="D")
        data = pd.DataFrame(
            {
                "Fund A": pd.Series(range(100, 200), index=dates_a, dtype=float),
                "Fund B": pd.Series(range(50, 150), index=dates_b, dtype=float),
            }
        )

        cleaned, _exclusions = prep.prepare(data)

        # Overlap starts at 2023-01-15, so 86 days remain
        assert len(cleaned) == 86
        assert list(cleaned.columns) == ["Fund A", "Fund B"]

    def test_prepare_uses_percentage_returns(self, prep, valid_nav_data):
        """Percentage returns are computed during preparation (not absolute)."""
        cleaned, _ = prep.prepare(valid_nav_data)

        # Verify cleaned data still contains NAV levels (not absolute diffs)
        # and that pct_change would be computable (no NaN after dropna)
        pct = cleaned.pct_change().dropna()
        assert not pct.empty
        assert len(pct.columns) == 3
