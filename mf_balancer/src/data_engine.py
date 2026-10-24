import os
import requests
from datetime import datetime, timedelta
import pandas as pd
from mftool import Mftool
from kiteconnect import KiteConnect

AMFI_NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


class DataEngine:
    def __init__(self, api_key=None, access_token=None):
        self.mftool = Mftool()
        if api_key and access_token:
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
        else:
            self.kite = None

        # Cache scheme codes: {scheme_code: "Scheme Name - Plan - Option"}
        self.scheme_codes = self.mftool.get_scheme_codes()

        # Build ISIN → {scheme_code, plan, option} mapping from AMFI NAVAll.txt
        # ISIN is a unique, unambiguous identifier — unlike fund names which vary
        # between Zerodha and AMFI.
        self.isin_to_code = self._build_isin_to_code_map()

    def _build_isin_to_code_map(self):
        """
        Fetch AMFI NAVAll.txt and build a mapping from ISIN to scheme metadata.

        AMFI NAVAll.txt format (semicolon-separated):
          Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;NAV;Date

        Returns:
            dict: {isin: {"code": str, "plan": str, "option": str}}
        """
        isin_map = {}
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
        except Exception as e:
            print(f"[yellow]Warning[/yellow]: Could not build ISIN map from AMFI: {e}")

        return isin_map

    def _validate_plan_option(self, scheme_meta, fund_name):
        """
        Validate that a matched scheme matches the expected plan type from the fund name.

        Prevents incorrect matches such as Parag Parikh Conservative Hybrid Fund
        being matched to Parag Parikh ELSS Tax Saver Fund.

        Args:
            scheme_meta: dict with "code", "plan", "option" from ISIN map
            fund_name: the Zerodha fund name (e.g. "... - DIRECT PLAN")

        Returns:
            bool: True if the scheme's plan/option is compatible with the fund name
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
        if "dividend" in name_lower and "idcw" not in option:
            return False

        return True

    def get_scheme_code_for_fund(self, fund_name, isin=None):
        """
        Find the AMFI Scheme Code for a given fund.

        Strategy (in order of reliability):
        1. ISIN-based exact match (primary) — ISIN is a unique identifier,
           validated against plan/option to prevent cross-plan mismatches.
        2. Strict name-based match (fallback) — only when ISIN lookup fails,
           with plan/option validation to prevent incorrect name-only matches.

        Args:
            fund_name: Zerodha fund name (e.g. "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN")
            isin: ISIN code from Zerodha holdings (optional but preferred)

        Returns:
            str or None: AMFI scheme code, or None if no valid match found
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
                    print(
                        f"  [yellow]Warning[/yellow]: ISIN {isin} matched scheme "
                        f"{scheme_meta['code']} but plan/option validation failed "
                        f"for '{fund_name}'. Skipping ISIN match."
                    )
                    return None
            # ISIN not found in AMFI map — fall through to name matching

        # --- Strategy 2: Strict name-based match (fallback) ---
        if not fund_name:
            return None

        query = fund_name.lower().replace("-", " ").replace("  ", " ").strip()
        query_tokens = set(query.split())

        best_match_code = None
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
                    (isin for isin, meta in self.isin_to_code.items() if meta["code"] == best_match_code),
                    None,
                ),
                {"code": best_match_code, "plan": "", "option": ""},
            )

            if self._validate_plan_option(scheme_meta, fund_name):
                return best_match_code

        return None

    def get_historical_nav(self, scheme_code, years=3):
        """Fetch historical NAV for a given scheme code."""
        # Note: mftool variable naming is a bit non-standard, but this works
        data = self.mftool.get_scheme_historical_nav(scheme_code)
        
        if not data or 'data' not in data:
            raise ValueError(f"Could not fetch data for scheme {scheme_code}")

        df = pd.DataFrame(data['data'])
        df['date'] = pd.to_datetime(df['date'], format='%d-%m-%Y')
        df['nav'] = pd.to_numeric(df['nav'])
        df = df.set_index('date').sort_index()
        
        # Filter for the requested period
        start_date = datetime.now() - timedelta(days=years*365)
        df = df[df.index >= start_date]
        
        return df['nav']

    def get_portfolio_holdings(self):
        """Fetch current mutual fund holdings from Zerodha."""
        if not self.kite:
            raise ValueError("Kite Connect not initialized")
        
        # Correctly fetch MF holdings
        try:
            holdings = self.kite.mf_holdings()
        except Exception as e:
            # Fallback or error handling
            print(f"Error fetching MF holdings: {e}")
            return pd.DataFrame()

        mf_holdings = []
        for h in holdings:
            # Structure: 
            # {'tradingsymbol': 'INF...', 'fund': 'Name', 'quantity': ...}
            # We use 'tradingsymbol' (which is ISIN/Code) as the identifier
            mf_holdings.append({
                'tradingsymbol': h.get('fund', h['tradingsymbol']), # Use readable name if available
                'isin': h['tradingsymbol'], # In MF response, tradingsymbol is often the ISIN
                'quantity': h['quantity'],
                'last_price': h['last_price'],
                'average_price': h['average_price'],
                'value': h['quantity'] * h['last_price']
            })
        
        return pd.DataFrame(mf_holdings)

    def get_scheme_details(self, scheme_code):
        return self.mftool.get_scheme_details(scheme_code)

if __name__ == "__main__":
    # Test stub
    de = DataEngine()
    # Example: Mirae Asset Large Cap Fund (Direct Growth) - Code 118825 (Check codes on AMFI)
    # This is just a test to see if mftool works
    try:
        nav = de.get_historical_nav('118825', years=1)
        print(f"Fetched {len(nav)} IDCW records for 118825")
    except Exception as e:
        print(f"Error: {e}")
