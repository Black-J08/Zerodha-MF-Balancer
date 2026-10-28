# Mutual Fund Balancer (Advisory Mode)

A Python-based tool to automate the rebalancing of your Mutual Fund portfolio using Modern Portfolio Theory (MPT). It operates in an **Advisory Mode**, generating actionable buy/sell reports to help you systematically transfer capital from a Debt Fund to an optimal Equity portfolio on Zerodha Coin.

## 🚀 Features

-   **Robust Optimization**:
    -   Uses **Ledoit-Wolf Shrinkage** for covariance estimation, ensuring mathematically stable portfolios even with limited data.
    -   Calculates **Maximum Sharpe Ratio** portfolio (Risk-Free Rate: 7%).
-   **Smart Data Engine**:
    -   Fetches real-time holdings directly from **Zerodha Kite**.
    -   Automatically fuzzy-matches your Zerodha funds to AMFI Scheme Codes.
    -   Retrieves historical NAV data for precise calculations.
    -   **Auto-Recovery**: Intelligently handles funds with short or missing history to ensure optimization never crashes.
    -   **Data Transparency**: Exports all intermediate data (NAV history, Covariance Matrix, Expected Returns) to `data/` for inspection.
-   **Interactive Source Selection**: Automatically lists your debt funds and lets you pick the "Master Source" for capital deployment.
-   **Flexible Execution**:
    -   **Static Monthly STP**: Generates a set-and-forget monthly transfer plan.
    -   **Dynamic Optimization**: Offers a re-runnable mode that adjusts transfers based on market conditions (buy the dip).
-   **Target Duration STP**: Implements a "Convergence Strategy" to deplete your debt capital over a fixed period (e.g., 12 months) while keeping your portfolio balanced.
-   **Automated Authentication**: Seamlessly handles Zerodha login flows and token management.

## 🛠️ Setup

### 1. Prerequisites
-   Python 3.10+
-   A Zerodha Kite Connect API account (API Key & Secret).

### 2. Installation
Clone the repository and install dependencies:
```bash
git clone https://github.com/yourusername/mf-balancer.git
cd mf-balancer
uv sync
```

### 3. Configuration
Copy `.env.example` to `.env` and fill in your Zerodha credentials:

```bash
cp .env.example .env
```

Then edit `.env` with your API key and secret:
```env
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
```

### Authentication Redirect URL (optional)
For automatic `request_token` capture, configure a redirect URL in your Zerodha developer console and add it to `.env`:

```env
KITE_REDIRECT_URL=http://127.0.0.1:61035/callback
```

The redirect URL must include an explicit port and a non-empty callback path (e.g., `/callback`). When configured, the login flow starts a lightweight local callback server that automatically captures the `request_token` from Zerodha's redirect. If the callback server cannot start or times out, the tool falls back to the manual entry flow where you paste the `request_token` (or the full redirect URL) yourself.

The `.env` file can be placed in either:
- **The current directory** where you run `mf-balancer` (takes precedence), or
- **The project root directory** (fallback if not found in CWD).

Alternatively, you can export `KITE_API_KEY` and `KITE_API_SECRET` as environment variables instead of using a `.env` file. If both are already set in the environment, `.env` loading is skipped entirely.

To run from a directory other than the project root, set `MF_BALANCER_HOME` to the project root path:

```bash
export MF_BALANCER_HOME=/path/to/mf-balancer
mf-balancer
```

## 🖥️ Usage

Run the main script from any directory:
```bash
mf-balancer
```

### Where files are created
-   **`.env`**: Loaded from the current directory first, then from the project root. If no `.env` is found and credentials are not in the environment, the tool will raise an error.
-   **`data/`**: Created under the directory where `.env` was loaded from (current directory or project root). Never created inside a virtual environment or site-packages.
-   **`output/`**: Always created in the **current directory** where you run the command. Reports are saved to `output/report_YYYY-MM-DD_....md`.

### What happens next?
1.  **Login**: If your session is expired, it will guide you to log in via your browser.
    -   If `KITE_REDIRECT_URL` is configured in `.env`, a lightweight local callback server automatically captures the `request_token` from Zerodha's redirect.
    -   Otherwise (or if the callback server is unavailable), you manually paste the `request_token` or the full redirect URL.
2.  **Portfolio Fetch**: It downloads your current mutual fund holdings.
3.  **Source Selection**: You will see a table of your funds. Enter the ID of the **Debt Fund** you want to use as the source of money.
4.  **Optimization**: The script fetches historical data, calculates the optimal equity split, and determines the exact transfer amounts.
5.  **Report**: A detailed Markdown report is saved to `output/report_YYYY-MM-DD_....md` in the current directory.
    -   Includes a **Portfolio Health Check** comparing your current stats vs. the optimized portfolio (Sharpe, Sortino, Drawdown).
    -   Provides a clear **Monthly STP Plan**.

## 📊 The Strategy: Target Duration Convergence

Unlike a simple SIP, this tool uses a dynamic **Target Duration** approach:
1.  It calculates the ideal "Target Value" for each equity fund based on MPT weights.
2.  It looks at your *current* value and the *remaining* debt capital.
3.  It calculates how much to transfer *this month* so that after `N` months, your portfolio perfectly converges to the optimal weights.

### 🎛️ Optimization Strategies
The tool now asks you to choose a strategy at runtime:

#### 1. Maximum Sharpe Ratio (Standard)
-   **Goal**: Mathematically perfect portfolio.
-   **Result**: Highest possible return per unit of risk.
-   **Behavior**: May allocate 0% to many funds if they don't contribute to the "Perfect" mix. Best for pure math lovers.

#### 2. Constrained Optimization (Diversified)
-   **Goal**: Best possible portfolio *within your comfort zone*.
-   **Reasoning**: "I want the math, but I don't want 50% of my money in one fund."
-   **Configuration**: You set:
    -   **Max Weight**: E.g., `0.20` (No fund gets > 20%).
    -   **Min Weight**: E.g., `0.01` (Every fund gets at least 1%).

### 📅 Execution Strategy Options

The tool provides two ways to execute the advice, catering to different management styles:

#### Option A: "Set and Forget" (Static STP)
-   **What**: The report generates a fixed "Monthly Installment" plan for your target duration (e.g., 12 months).
-   **Action**: You log into your broker **once** and set up official STP instructions for these amounts.
-   **Pros**: Zero maintenance. You don't need to run the script again for a year.
-   **Cons**: Does not react to market crashes or rallies.

#### Option B: "Dynamic Optimization" (Recommended)
-   **What**: You treat the output as a "This Month Only" instruction.
-   **Action**: 
    1.  Execute the transfer for **this month only**.
    2.  Run the script again **next month**.
-   **Pros**: **Superior Performance**. The algorithm sees the new NAVs next month.
    -   *Market Crash?* It will tell you to transfer **more** to buy low.
    -   *Market Rally?* It will tell you to transfer **less** to avoid buying high.
-   **Cons**: Requires 5 minutes of effort once a month.

## ⚠️ Troubleshooting
-   **"Insufficient History"**: If you have a brand new fund (<30 days old), the script will automatically exclude it from optimization to prevent errors.
-   **Login Failed**: Double-check your API Key and Secret in `.env`.

## 🤝 Contributing
Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
