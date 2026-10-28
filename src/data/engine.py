"""DataEngine: NAV fetching, scheme code resolution, and ISIN mapping.

Central data access component for MF Balancer. Handles:
- Building and caching the ISIN → scheme code mapping from AMFI NAVAll.txt
- Resolving Zerodha fund names to AMFI scheme codes (ISIN primary, name fallback)
- Fetching historical NAV data via mftool
- Fetching portfolio holdings from Zerodha Kite Connect
"""

import pandas as pd
import requests
from kiteconnect import KiteConnect
from mftool import Mftool

from src.core.logging import get_logger
from src.core.settings import Settings
from src.data.holdings import get_portfolio_holdings
from src.data.nav import get_historical_nav

AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"

logger = get_logger(__name__)


class DataEngine:
    """Data access engine for mutual fund portfolio operations.

    Args:
        config: Application configuration containing API credentials and paths.
    """

    def __init__(self, config: Settings, kite: KiteConnect | None = None):
        self.config = config
        self.mftool = Mftool()

        # Use the provided authenticated KiteConnect instance (e.g. from
        # authenticate()) if available; otherwise build one from config.
        if kite is not None:
            self.kite = kite
        elif config.kite_api_key and config.kite_access_token:
            self.kite = KiteConnect(api_key=config.kite_api_key)
            self.kite.set_access_token(config.kite_access_token)
        else:
            self.kite = None

        # Cache scheme codes: {scheme_code: "Scheme Name - Plan - Option"}
        self.scheme_codes = self.mftool.get_scheme_codes()

        # Build ISIN → {scheme_code, plan, option} mapping from AMFI NAVAll.txt
        # ISIN is a unique, unambiguous identifier — unlike fund names which vary
        # between Zerodha and AMFI.
        self.isin_to_code = self._build_isin_to_code_map()

    def _build_isin_to_code_map(self) -> dict:
        """Fetch AMFI NAVAll.txt and build a mapping from ISIN to scheme metadata.

        AMFI NAVAll.txt format (semicolon-separated):
          Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;NAV;Date

        Returns:
            dict: {isin: {"code": str, "plan": str, "option": str}}
        """
        isin_map: dict = {}
        try:
            headers = {"User-Agent": "Chrome/95.0.4638.69"}
            response = requests.get(AMFI_NAV_ALL_URL, headers=headers, timeout=30)
            response.raise_for_status()
            for line in response.text.split("\n"):
                if ";" not in line:
                    continue
                parts = line.split(";")
                if len(parts) < 6:
                    continue
                scheme_code = parts[0].strip()
                isin_growth = parts[1].strip() if len(parts) > 1 else ""
                isin_reinvest = parts[2].strip() if len(parts) > 2 else ""
                plan = parts[4].strip() if len(parts) > 4 else ""
                option = parts[5].strip() if len(parts) > 5 else ""

                # Map both ISIN Div Payout/Growth and ISIN Div Reinvestment to the same scheme
                for isin in (isin_growth, isin_reinvest):
                    if isin and isin != "-":
                        isin_map[isin] = {
                            "code": scheme_code,
                            "plan": plan,
                            "option": option,
                        }
        except Exception:
            logger.exception("Could not build ISIN map from AMFI")

        return isin_map

    def _validate_plan_option(self, scheme_meta: dict, fund_name: str) -> bool:
        """Validate that a matched scheme matches the expected plan type from the fund name.

        Prevents incorrect matches such as Parag Parikh Conservative Hybrid Fund
        being matched to Parag Parikh ELSS Tax Saver Fund.

        Args:
            scheme_meta: dict with "code", "plan", "option" from ISIN map.
            fund_name: The Zerodha fund name (e.g. "... - DIRECT PLAN").

        Returns:
            True if the scheme's plan/option is compatible with the fund name.
        """
        if not scheme_meta:
            return False

        name_lower = fund_name.lower()
        plan = scheme_meta.get("plan", "").lower()
        option = scheme_meta.get("option", "").lower()

        # If the fund name specifies a plan, the scheme must match it
        if "direct" in name_lower and "direct" not in plan:
            return False
        if "regular" in name_lower and "regular" not in plan:
            return False

        # If the fund name specifies an option, the scheme must match it
        if "growth" in name_lower and "growth" not in option:
            return False
        if "idcw" in name_lower and "idcw" not in option:
            return False

        return not ("dividend" in name_lower and "idcw" not in option)

    def get_scheme_code_for_fund(self, fund_name: str, isin: str | None = None) -> str | None:
        """Find the AMFI Scheme Code for a given fund.
        Strategy (in order of reliability):
        1. ISIN-based exact match (primary) — ISIN is a unique identifier,
           validated against plan/option to prevent cross-plan mismatches.
        2. Strict name-based match (fallback) — only when ISIN lookup fails,
           with plan/option validation to prevent incorrect name-only matches.

        Args:
            fund_name: Zerodha fund name (e.g. "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN").
            isin: ISIN code from Zerodha holdings (optional but preferred).

        Returns:
            AMFI scheme code, or None if no valid match found.
        """
        # --- Strategy 1: ISIN-based exact match (primary) ---
        if isin:
            scheme_meta = self.isin_to_code.get(isin)
            if scheme_meta:
                if self._validate_plan_option(scheme_meta, fund_name):
                    return scheme_meta["code"]
                else:
                    # ISIN matched but plan/option doesn't align — do not accept.
                    # Do NOT fall through to name matching: ISIN is a unique
                    # identifier, and a plan/option mismatch means the fund
                    # identity is ambiguous. Returning None is safer than
                    # matching a different fund by similar name.
                    logger.warning(
                        "ISIN %s matched scheme %s but plan/option validation "
                        "failed for '%s'. Skipping ISIN match.",
                        isin,
                        scheme_meta["code"],
                        fund_name,
                    )
                    return None
            # ISIN not found in AMFI map — fall through to name matching

        # --- Strategy 2: Strict name-based match (fallback) ---
        if not fund_name:
            return None

        query = fund_name.lower().replace("-", " ").replace("  ", " ").strip()
        query_tokens = set(query.split())

        best_match_code: str | None = None
        best_match_score = 0

        for code, name in self.scheme_codes.items():
            name_lower = name.lower().replace("-", " ").replace("  ", " ")
            name_tokens = set(name_lower.split())
            intersection = query_tokens.intersection(name_tokens)

            if not intersection:
                continue

            score = len(intersection)

            # Penalty for missing key terms like 'Direct' if present in query
            if "direct" in query and "direct" not in name_lower:
                score -= 5
            if "growth" in query and "growth" not in name_lower:
                score -= 5

            if score > best_match_score:
                best_match_score = score
                best_match_code = code

        # Threshold: all-but-one tokens must match (strict)
        if best_match_score >= len(query_tokens) - 1:
            # Validate plan/option even for name-based matches.
            # mftool's scheme_codes values are "Scheme Name - Option" (no plan field),
            # so plan/option info comes from the ISIN map if available.
            scheme_meta = self.isin_to_code.get(
                next(
                    (
                        isin
                        for isin, meta in self.isin_to_code.items()
                        if meta["code"] == best_match_code
                    ),
                    None,
                ),
                {"code": best_match_code, "plan": "", "option": ""},
            )

            if self._validate_plan_option(scheme_meta, fund_name):
                return best_match_code

        return None

    def get_historical_nav(self, scheme_code: str, years: int = 3) -> pd.Series:
        """Fetch historical NAV for a given scheme code.

        Args:
            scheme_code: AMFI scheme code.
            years: Number of years of history to fetch (default 3).

        Returns:
            A :class:`pandas.Series` with dates as index and NAV values.
        """
        return get_historical_nav(self.mftool, scheme_code, years=years)

    def get_portfolio_holdings(self) -> pd.DataFrame:
        """Fetch current mutual fund holdings from Zerodha.

        Returns:
            A :class:`pandas.DataFrame` with holdings data, or empty
            DataFrame if Kite Connect is not initialized or on error.
        """
        if not self.kite:
            logger.error("Kite Connect not initialized")
            return pd.DataFrame()

        return get_portfolio_holdings(self.kite)

    def get_scheme_details(self, scheme_code: str):
        """Fetch scheme details from mftool.

        Args:
            scheme_code: AMFI scheme code.

        Returns:
            Scheme details dict from mftool.
        """
        return self.mftool.get_scheme_details(scheme_code)
