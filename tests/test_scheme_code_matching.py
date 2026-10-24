"""
Regression tests for scheme code matching fix.

Root cause: Zerodha fund names (from kite.mf_holdings()) don't match AMFI scheme
names due to a strict token-intersection threshold in get_scheme_code_for_fund().
Every fund failed to match, resulting in empty nav_data and the
"Critical Error: Could not fetch NAV data for ANY equity fund" error.

Fix: ISIN-based exact matching as primary method (ISIN is a unique identifier),
with plan/option validation to prevent cross-plan mismatches. Name-based matching
is a strict fallback only.

These tests verify:
1. ISIN-based matching correctly resolves scheme codes
2. Plan/option validation prevents incorrect matches (e.g. Conservative Hybrid vs ELSS)
3. Name-based fallback works when ISIN is unavailable
4. Funds from the original bug report now resolve correctly
"""

import sys
import os

# Add workspace to path so we can import mf_balancer
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch, MagicMock
from mf_balancer.src.data_engine import DataEngine


class TestSchemeCodeMatching:
    """Regression tests for get_scheme_code_for_fund ISIN-based matching."""

    def setup_method(self):
        """Set up a DataEngine with mocked mftool and ISIN map."""
        self.de = DataEngine.__new__(DataEngine)
        self.de.mftool = MagicMock()
        self.de.kite = None

        # scheme_codes: {code: "Scheme Name - Plan - Option"}
        self.de.scheme_codes = {
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
        self.de.isin_to_code = {
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

    # ------------------------------------------------------------------
    # ISIN-based matching (primary method)
    # ------------------------------------------------------------------

    def test_isin_match_returns_correct_scheme_code(self):
        """ISIN-based exact match should return the correct scheme code."""
        code = self.de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", isin="INF123456"
        )
        assert code == "123456", f"Expected 123456, got {code}"

    def test_isin_match_works_for_all_bug_report_funds(self):
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
            code = self.de.get_scheme_code_for_fund(fund_name, isin=isin)
            assert code is not None, f"ISIN match failed for {fund_name} (ISIN: {isin})"

    def test_isin_match_without_fund_name_still_works(self):
        """ISIN match should work even if fund_name is empty/None."""
        code = self.de.get_scheme_code_for_fund("", isin="INF123456")
        assert code == "123456", f"Expected 123456, got {code}"

    # ------------------------------------------------------------------
    # Plan/option validation (prevents incorrect matches)
    # ------------------------------------------------------------------

    def test_plan_validation_rejects_regular_plan_when_direct_requested(self):
        """A Direct Plan request must not match a Regular Plan scheme."""
        code = self.de.get_scheme_code_for_fund(
            "SOME FUND - DIRECT PLAN", isin="INF123464"
        )
        assert code is None, (
            f"Expected None (Regular Plan rejected for Direct request), got {code}"
        )

    def test_option_validation_rejects_idcw_when_growth_requested(self):
        """A Growth request must not match an IDCW scheme."""
        code = self.de.get_scheme_code_for_fund(
            "SOME FUND - DIRECT PLAN - GROWTH", isin="INF123465"
        )
        assert code is None, (
            f"Expected None (IDCW rejected for Growth request), got {code}"
        )

    def test_conservative_hybrid_not_matched_to_elss(self):
        """
        CRITICAL: Parag Parikh Conservative Hybrid Fund must NOT match
        Parag Parikh ELSS Tax Saver Fund even though they share the AMC name.

        This is the exact scenario from the user's requirement: never match
        funds solely by similar names — validate scheme identity and plan type.
        """
        # Conservative Hybrid has ISIN INF123457 -> scheme 123457
        # ELSS has ISIN INF123458 -> scheme 123458
        # If we look up Conservative Hybrid by its own ISIN, we must get 123457, not 123458
        code = self.de.get_scheme_code_for_fund(
            "PARAG PARIKH CONSERVATIVE HYBRID FUND - DIRECT PLAN", isin="INF123457"
        )
        assert code == "123457", (
            f"Conservative Hybrid matched to wrong scheme: {code} (expected 123457)"
        )
        assert code != "123458", (
            "Conservative Hybrid must NOT match ELSS Tax Saver Fund"
        )

    # ------------------------------------------------------------------
    # Name-based fallback (when ISIN unavailable)
    # ------------------------------------------------------------------

    def test_name_fallback_works_when_isin_not_provided(self):
        """Name-based matching should work as fallback when ISIN is None."""
        code = self.de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN"
        )
        assert code == "123456", f"Expected 123456, got {code}"

    def test_name_fallback_rejects_wrong_plan(self):
        """Name-based fallback must still validate plan type."""
        code = self.de.get_scheme_code_for_fund(
            "REGULAR PLAN FUND - DIRECT PLAN"
        )
        # scheme 123464 is "Regular Plan Fund - Regular Plan - Growth Option"
        # Request is Direct Plan, so it should be rejected
        assert code is None, (
            f"Expected None (Regular Plan rejected for Direct request), got {code}"
        )

    def test_no_match_returns_none(self):
        """Completely unknown fund should return None."""
        code = self.de.get_scheme_code_for_fund(
            "NONEXISTENT FUND THAT DOES NOT EXIST - DIRECT PLAN", isin="INF999999"
        )
        assert code is None, f"Expected None, got {code}"

    def test_isin_not_in_map_falls_back_to_name(self):
        """If ISIN is not in the AMFI map, fall back to name matching."""
        # INF999999 is not in isin_to_code, so it falls back to name matching
        code = self.de.get_scheme_code_for_fund(
            "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", isin="INF999999"
        )
        assert code == "123456", f"Expected 123456 (name fallback), got {code}"


if __name__ == "__main__":
    # Run all test methods manually (no pytest dependency)
    test = TestSchemeCodeMatching()
    test.setup_method()
    passed = 0
    failed = 0
    for name in dir(test):
        if name.startswith("test_"):
            test.setup_method()  # fresh state for each test
            try:
                getattr(test, name)()
                print(f"PASS: {name}")
                passed += 1
            except AssertionError as e:
                print(f"FAIL: {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"ERROR: {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests")
    sys.exit(1 if failed else 0)
