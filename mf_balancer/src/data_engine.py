import os
from datetime import datetime, timedelta
import pandas as pd
from mftool import Mftool
from kiteconnect import KiteConnect

class DataEngine:
    def __init__(self, api_key=None, access_token=None):
        self.mftool = Mftool()
        if api_key and access_token:
            self.kite = KiteConnect(api_key=api_key)
            self.kite.set_access_token(access_token)
        else:
            self.kite = None
            
        # Cache scheme codes
        self.scheme_codes = self.mftool.get_scheme_codes()

    def get_scheme_code_for_fund(self, fund_name):
        """
        Attempts to find the AMFI Scheme Code for a given fund name from Zerodha.
        Strategy:
        1. Exact Match case-insensitive
        2. Token set match (most words present)
        3. Priority for 'Direct' and 'Growth' plans
        """
        if not fund_name:
            return None
            
        # Pre-processing
        query = fund_name.lower().replace("-", " ").replace("  ", " ").strip()
        query_tokens = set(query.split())
        
        best_match_code = None
        best_match_score = 0
        
        for code, name in self.scheme_codes.items():
            name_lower = name.lower().replace("-", " ").replace("  ", " ")
            
            # Zerodha names are usually "Fund Name - Plan - Option"
            # We prioritize Direct Growth plans as they are most common for kite users
            
            # Simple scoring: Intersection over Union (Jaccard-ish)
            name_tokens = set(name_lower.split())
            intersection = query_tokens.intersection(name_tokens)
            
            if not intersection:
                continue
                
            score = len(intersection)
            
            # Penalty for missing key terms like 'Direct' if present in query
            if 'direct' in query and 'direct' not in name_lower:
                score -= 5
            if 'growth' in query and 'growth' not in name_lower:
                score -= 5
                
            if score > best_match_score:
                best_match_score = score
                best_match_code = code
        
        # Threshold: meaningful match
        if best_match_score >= len(query_tokens) - 1: # Allow 1 missing word
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
