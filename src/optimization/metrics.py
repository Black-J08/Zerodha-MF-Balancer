"""Portfolio performance metrics.

Provides advanced risk and return metrics for portfolio analysis:
Sharpe Ratio, Sortino Ratio, Max Drawdown, and Value at Risk (VaR).
"""

import pandas as pd


def get_advanced_stats(
    nav_data: pd.DataFrame,
    weights: dict,
    risk_free_rate: float = 0.07,
) -> dict:
    """Calculate advanced risk metrics for a given set of weights.

    Computes Expected Return, Volatility, Sharpe Ratio, Sortino Ratio,
    Max Drawdown, and Value at Risk (95% confidence).

    Args:
        nav_data: DataFrame with dates as index and fund names as columns,
            containing historical NAV data.
        weights: Mapping of fund name to target weight (0.0 to 1.0).
        risk_free_rate: Annual risk-free rate (default 0.07 = 7%).

    Returns:
        Dictionary with keys: Expected Return, Volatility, Sharpe Ratio,
        Sortino Ratio, Max Drawdown, VaR (95%).
    """
    from pypfopt import EfficientFrontier

    # 1. Basic Stats via EfficientFrontier
    mu = __import__("pypfopt.expected_returns", fromlist=["mean_historical_return"]).mean_historical_return(
        nav_data.dropna()
    )
    S = __import__("pypfopt.risk_models", fromlist=["CovarianceShrinkage"]).CovarianceShrinkage(
        nav_data.dropna()
    ).ledoit_wolf()

    ef = EfficientFrontier(mu, S)
    ef.set_weights(weights)
    ret, vol, sharpe = ef.portfolio_performance(verbose=False)

    # 2. Historical Portfolio Returns (reconstructed)
    pct_change = nav_data.dropna().pct_change().dropna()

    # Filter pct_change to only include assets in weights
    list(set(weights.keys()) & set(pct_change.columns))

    portfolio_returns = pd.Series(0, index=pct_change.index)
    for asset, weight in weights.items():
        if asset in pct_change.columns:
            portfolio_returns += pct_change[asset] * weight

    # 3. Sortino Ratio (Downside Risk)
    target_return = 0
    downside_returns = portfolio_returns[portfolio_returns < target_return]
    downside_deviation = downside_returns.std() * (252**0.5)  # Annualized

    sortino = (ret - risk_free_rate) / downside_deviation if downside_deviation != 0 else 0

    # 4. Max Drawdown
    cumulative_returns = (1 + portfolio_returns).cumprod()
    peak = cumulative_returns.cummax()
    drawdown = (cumulative_returns - peak) / peak
    max_drawdown = drawdown.min()

    # 5. Value at Risk (VaR) - 95% Confidence
    var_95 = portfolio_returns.quantile(0.05)

    return {
        "Expected Return": ret,
        "Volatility": vol,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Max Drawdown": max_drawdown,
        "VaR (95%)": var_95,
    }
