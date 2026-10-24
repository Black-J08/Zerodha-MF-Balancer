"""Unit tests for DataEngine.

Tests scheme code matching, ISIN-based resolution,
and plan/option validation.
"""

from unittest.mock import MagicMock

import pytest

from src.data.engine import DataEngine


@pytest.fixture
def de():
    """Create a DataEngine with mocked mftool and ISIN map."""
    engine = DataEngine.__new__(DataEngine)
    engine.mftool = MagicMock()
    engine.kite = None

    # scheme_codes: {code: "Scheme Name - Plan - Option"}
    engine.scheme_codes = {
        "123456": "Parag Parikh Flexi Cap Fund - Direct Plan - Growth Option",
        "123457": "Parag Parikh Conservative Hybrid Fund - Direct Plan - Growth Option",
        "123458": "Parag Parikh ELSS Tax Saver Fund - Direct Plan - Growth Option",
        "123459": "Motilal Oswal Multi Cap Fund - Direct Plan - Growth Option",
        "123460": "Quant Large & Mid Cap Fund - Direct Plan - Growth Option",
        "123461": "ICICI Prudential Floating Interest Rates Fund - Direct Plan - Growth Option",
        "123462": "ICICI Prudential Liquid Fund - Direct Plan - Growth Option",
        "123463": "Edelweiss Mid Cap Fund - Direct Plan - Growth Option",
        "123464": "Regular Plan Fund - Regular Plan - Growth Option",
        "123465": "IDCW Option Fund - Direct Plan - IDCW Option",
    }

    # isin_to_code: {isin: {"code": ..., "plan": ..., "option": ...}}
    engine.isin_to_code = {
        "INF123456": {"code": "123456", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123457": {"code": "123457", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123458": {"code": "123458", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123459": {"code": "123459", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123460": {"code": "123460", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123461": {"code": "123461", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123462": {"code": "123462", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123463": {"code": "123463", "plan": "Direct Plan", "option": "Growth Option"},
        "INF123464": {"code": "123464", "plan": "Regular Plan", "option": "Growth Option"},
        "INF123465": {"code": "123465", "plan": "Direct Plan", "option": "IDCW Option"},
    }

    return engine


class TestDataEngine:
    """Tests for DataEngine class."""

    def test_isin_match_returns_correct_scheme_code(self, de):
        """ISIN-based exact match should return the correct scheme code."""
        code = de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", isin="INF123456"
        )
        assert code == "123456", f"Expected 123456, got {code}"

    def test_isin_match_works_for_all_bug_report_funds(self, de):
        """All funds from the original bug report should resolve via ISIN."""
        fund_isin_pairs = [
            ("PARAG PARIKH CONSERVATIVE HYBRID FUND - DIRECT PLAN", "INF123457"),
            ("MOTILAL OSWAL MULTI CAP FUND - DIRECT PLAN", "INF123459"),
            ("QUANT LARGE & MID CAP FUND - DIRECT PLAN", "INF123460"),
            ("ICICI PRUDENTIAL FLOATING INTEREST RATES FUND - DIRECT PLAN", "INF123461"),
            ("ICICI PRUDENTIAL LIQUID FUND - DIRECT PLAN", "INF123462"),
            ("EDELWEISS MID CAP FUND - DIRECT PLAN", "INF123463"),
        ]
        for fund_name, isin in fund_isin_pairs:
            code = de.get_scheme_code_for_fund(fund_name, isin=isin)
            assert code is not None, f"ISIN match failed for {fund_name} (ISIN: {isin})"

    def test_isin_match_without_fund_name_still_works(self, de):
        """ISIN match should work even if fund_name is empty/None."""
        code = de.get_scheme_code_for_fund("", isin="INF123456")
        assert code == "123456", f"Expected 123456, got {code}"

    def test_plan_validation_rejects_regular_plan_when_direct_requested(self, de):
        """A Direct Plan request must not match a Regular Plan scheme."""
        code = de.get_scheme_code_for_fund(
            "SOME FUND - DIRECT PLAN", isin="INF123464"
        )
        assert code is None, (
            f"Expected None (Regular Plan rejected for Direct request), got {code}"
        )

    def test_option_validation_rejects_idcw_when_growth_requested(self, de):
        """A Growth request must not match an IDCW scheme."""
        code = de.get_scheme_code_for_fund(
            "SOME FUND - DIRECT PLAN - GROWTH", isin="INF123465"
        )
        assert code is None, (
            f"Expected None (IDCW rejected for Growth request), got {code}"
        )

    def test_conservative_hybrid_not_matched_to_elss(self, de):
        """
        CRITICAL: Parag Parikh Conservative Hybrid Fund must NOT match
        Parag Parikh ELSS Tax Saver Fund even though they share the AMC name.
        """
        code = de.get_scheme_code_for_fund(
            "PARAG PARIKH CONSERVATIVE HYBRID FUND - DIRECT PLAN", isin="INF123457"
        )
        assert code == "123457", (
            f"Conservative Hybrid matched to wrong scheme: {code} (expected 123457)"
        )
        assert code != "123458", (
            "Conservative Hybrid must NOT match ELSS Tax Saver Fund"
        )

    def test_name_fallback_works_when_isin_not_provided(self, de):
        """Name-based matching should work as fallback when ISIN is None."""
        code = de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN"
        )
        assert code == "123456", f"Expected 123456, got {code}"

    def test_name_fallback_rejects_wrong_plan(self, de):
        """Name-based fallback must still validate plan type."""
        code = de.get_scheme_code_for_fund(
            "REGULAR PLAN FUND - DIRECT PLAN"
        )
        # scheme 123464 is "Regular Plan Fund - Regular Plan - Growth Option"
        # Request is Direct Plan, so it should be rejected
        assert code is None, (
            f"Expected None (Regular Plan rejected for Direct request), got {code}"
        )

    def test_no_match_returns_none(self, de):
        """Completely unknown fund should return None."""
        code = de.get_scheme_code_for_fund(
            "NONEXISTENT FUND THAT DOES NOT EXIST - DIRECT PLAN", isin="INF999999"
        )
        assert code is None, f"Expected None, got {code}"

    def test_isin_not_in_map_falls_back_to_name(self, de):
        """If ISIN is not in the AMFI map, fall back to name matching."""
        # INF999999 is not in isin_to_code, so it falls back to name matching
        code = de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", isin="INF999999"
        )
        assert code == "123456", f"Expected 123456 (name fallback), got {code}"
