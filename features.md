# Features & Roadmap

## ✅ Implemented Features

### Core Logic
- [x] **Zerodha Kite Integration**: Fetches real-time mutual fund holdings using `kite.mf_holdings()`.
- [x] **historical Data Fetching**: Maps Zerodha fund names to AMFI codes and fetches NAV history via `mftool`.
- [x] **Robust Optimization (MPT)**: 
    - [x] Optimizes portfolio weights for **Maximum Sharpe Ratio** using `PyPortfolioOpt`.
    - [x] Uses **Ledoit-Wolf Shrinkage** for covariance estimation (Industry Standard stability).
    - [x] **Interactive Constrained Optimization**: Allows users to set **Min/Max limits** per fund (e.g., "Max 20%") to ensure diversification.
    - [x] **Detailed Portfolio Metrics**: Provides a side-by-side "Health Check" comparing your **Current vs. Optimized** portfolio on Sharpe Ratio, Sortino Ratio, and Max Drawdown.
- [x] **Target Duration STP**: Systematically transfers debt capital to equity to achieve optimal allocation over a set timeframe.

### User Experience
- [x] **Interactive CLI**: Easy-to-use command line interface with rich text tables.
- [x] **Interactive Auth**: Automated flow to handle Kite Connect login and token saving.
    - [x] **Callback Server**: Lightweight built-in HTTP callback server (derived from `KITE_REDIRECT_URL`) automatically captures the `request_token` from Zerodha's redirect and shuts down gracefully.
    - [x] **Manual Fallback**: Falls back to manual `request_token` entry (or full redirect URL with auto-extraction) if the callback server is unavailable or times out.
- [x] **Smart Source Selection**: Lets user pick any fund from their portfolio to act as the "Debt Source".
- [x] **Flexible Execution**:
    - [x] **Static Mode**: Generates a fixed monthly STP plan.
    - [x] **Dynamic Mode**: Supports month-on-month re-optimization.

### Robustness & Transparency
- [x] **Fuzzy Name Matching**: Intelligently maps varying fund names between Zerodha and AMFI.
- [x] **Data Gap Handling**: Automatically detecting and excluding funds with insufficient history (<30 days) to prevent optimization crashes.
- [x] **Dynamic Intersection**: Finds the common historical period for all selected funds to ensure accurate covariance calculation.
- [x] **Data Export**: Saves all intermediate data (`nav_history.csv`, `covariance_matrix.csv`, `expected_returns.csv`) to `data/` for user inspection.

## 🚀 Future Roadmap

### Short Term
- [ ] **Configurable STP Models**: Add "Capital Appreciation" and "Valuation Adjusted" STP modes.
- [ ] **PDF Reporting**: Generate beautiful PDF reports instead of Markdown.
- [ ] **Email Alerts**: Send the rebalancing report directly to email.

### Long Term
- [ ] **Direct Order Placement**: (Dependent on Zerodha API updates) Automate the actual placing of Buy/Sell orders.
- [ ] **Tax Harvesting**: Logic to identify and suggest tax-loss harvesting opportunities.
- [ ] **Goal Tracking**: Map portfolios to specific financial goals (e.g., "Retirement 2040").
