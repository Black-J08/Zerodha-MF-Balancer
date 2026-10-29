"""PortfolioService: application layer orchestrating domain modules.

Orchestrates the advisory workflow:
  fetch holdings → resolve scheme codes → fetch NAV history
  → calculate expected returns & covariance → optimize weights
  → calculate STP transfers → generate report

Authentication is handled by the presentation layer (CLI/API) before
calling the service. The service assumes settings already contain
valid credentials.

The service has no knowledge of presentation layers (CLI, API, UI).
All user interaction (prompts, console output) is handled by the
presentation layer that calls this service.
"""

import os
from dataclasses import dataclass

import pandas as pd

from src.allocation import Allocator
from src.core.logging import get_logger
from src.core.models import FundExclusion
from src.core.settings import Settings
from src.data import DataEngine
from src.optimization import PortfolioOptimizer
from src.reporting import Reporter

logger = get_logger(__name__)


@dataclass
class AdvisoryResult:
    """Result of the full advisory workflow.

    Attributes:
        optimal_weights: Mapping of fund name to target weight (0.0 to 1.0).
        transfers: Mapping of fund name to monthly transfer amount (INR).
        summary: Allocator summary dict (Total_Equity, Debt_Capital, Total_Projected).
        current_stats: Current portfolio advanced stats, or None.
        optimized_stats: Optimized portfolio advanced stats, or None.
        report_path: Path to the generated Markdown report.
        excluded_funds: List of :class:`FundExclusion` for funds excluded from
            optimization, each with a reason and optional detail.
        valid_funds: List of fund names included in optimization.
        debt_capital: Total debt capital used (INR).
        months: Planning horizon in months.
    """

    optimal_weights: dict[str, float]
    transfers: dict[str, float]
    summary: dict
    current_stats: dict | None
    optimized_stats: dict | None
    report_path: str
    excluded_funds: list[FundExclusion]
    valid_funds: list[str]
    debt_capital: float
    months: int


class PortfolioService:
    """Orchestrates domain modules for portfolio advisory operations.

    Args:
        settings: Application configuration.
        data_engine: Optional DataEngine instance (for testability/mocking).
            If not provided, one is created from settings.
    """

    def __init__(self, settings: Settings, data_engine: DataEngine | None = None):
        self.settings = settings
        self.data_engine = data_engine or DataEngine(settings)

    # ------------------------------------------------------------------
    # Full advisory workflow
    # ------------------------------------------------------------------

    def run_advisory(
        self,
        debt_capital: float | None,
        months: int,
        risk_free_rate: float,
        source_fund_name: str | None = None,
        weight_bounds: tuple[float, float] = (0.0, 1.0),
    ) -> AdvisoryResult:
        """Run the complete advisory workflow.

        Args:
            debt_capital: Total capital available in Debt Fund (INR).
                If None, the caller must provide source_fund_name.
            months: Number of months to deplete the debt capital.
            risk_free_rate: Risk-free rate for Sharpe Ratio (decimal).
            source_fund_name: Name of the debt fund to use as capital source.
                Required if debt_capital is None.
            weight_bounds: Tuple of (min_weight, max_weight) for each asset.

        Returns:
            AdvisoryResult containing all computed outputs.

        Raises:
            ValueError: If neither debt_capital nor source_fund_name is provided,
                or if no valid NAV data is available for optimization.
        """
        # --- 1. Authentication (handled by presentation layer before calling service) ---
        # The service assumes the settings already contain valid credentials.
        # Presentation layer (CLI/API) is responsible for calling authenticate() first.

        # --- 2. Portfolio Fetching ---
        holdings_df = self.data_engine.get_portfolio_holdings()
        if holdings_df.empty:
            raise ValueError(
                "No Mutual Fund holdings found in this Zerodha account!"
            )
        current_holdings = dict(zip(holdings_df["tradingsymbol"], holdings_df["value"]))
        fund_isin_map = dict(zip(holdings_df["tradingsymbol"], holdings_df["isin"]))

        # --- 3. Select Source Debt Fund ---
        if debt_capital is None:
            if source_fund_name is None:
                raise ValueError(
                    "Either debt_capital or source_fund_name must be provided."
                )
            if source_fund_name not in current_holdings:
                raise ValueError(
                    f"Source fund '{source_fund_name}' not found in holdings."
                )
            debt_capital = current_holdings[source_fund_name]

        # --- 4. Prepare Optimization Data (Exclude Debt Fund) ---
        equity_holdings = current_holdings.copy()
        if source_fund_name:
            equity_holdings.pop(source_fund_name, None)

        # --- 5. Fetch Real NAVs ---
        nav_data = pd.DataFrame()
        excluded_funds: list[FundExclusion] = []
        for fund_name in equity_holdings:
            isin = fund_isin_map.get(fund_name)
            code = self.data_engine.get_scheme_code_for_fund(fund_name, isin=isin)

            if code is None:
                excluded_funds.append(
                    FundExclusion(
                        fund_name=fund_name,
                        reason="Scheme code not found",
                        detail=None,
                    )
                )
                logger.warning(
                    "Could not map fund name to AMFI Code automatically for %s. Skipping.",
                    fund_name,
                )
                continue

            try:
                nav_series = self.data_engine.get_historical_nav(code)
                if nav_series.empty:
                    excluded_funds.append(
                        FundExclusion(
                            fund_name=fund_name,
                            reason="No NAV data returned",
                            detail=None,
                        )
                    )
                    logger.warning("No data returned for %s (Code: %s). Skipping.", fund_name, code)
                    continue

                if len(nav_series) < 30:
                    excluded_funds.append(
                        FundExclusion(
                            fund_name=fund_name,
                            reason="Insufficient history",
                            detail=f"{len(nav_series)} days found, 30 required",
                        )
                    )
                    logger.warning(
                        "Insufficient history (%d days) for %s. Need >30. Skipping.",
                        len(nav_series),
                        fund_name,
                    )
                    continue

                nav_data[fund_name] = nav_series
            except Exception:
                excluded_funds.append(
                    FundExclusion(
                        fund_name=fund_name,
                        reason="NAV fetch failed",
                        detail=None,
                    )
                )
                logger.exception("NAV fetch failed for %s", fund_name)

        valid_funds = nav_data.columns.tolist()
        if not valid_funds:
            raise ValueError(
                "Could not fetch NAV data for ANY equity fund. Cannot optimize."
            )

        # Pre-Optimization Data Cleaning
        current_len = len(nav_data.dropna())
        if current_len < 30:
            start_dates = nav_data.apply(lambda x: x.first_valid_index())
            max_start = start_dates.max()
            culprits = start_dates[start_dates == max_start].index.tolist()
            nav_data = nav_data.drop(columns=culprits)
            for culprit in culprits:
                excluded_funds.append(
                    FundExclusion(
                        fund_name=culprit,
                        reason="Dropped during data cleaning",
                        detail="Insufficient overlapping period",
                    )
                )
            valid_funds = nav_data.columns.tolist()

            if nav_data.dropna().empty:
                raise ValueError(
                    "Still no overlapping data after cleaning. Cannot optimize."
                )

        # Save Cleaned NAV Data for Inspection
        nav_export_path = os.path.join(self.settings.data_dir, "nav_history.csv")
        os.makedirs(os.path.dirname(nav_export_path), exist_ok=True)
        nav_data.to_csv(nav_export_path)
        logger.info("Saved historical NAV data to %s", nav_export_path)

        equity_holdings_optimized = {
            k: v for k, v in equity_holdings.items() if k in valid_funds
        }

        # --- 6. Optimize ---
        optimizer = PortfolioOptimizer(nav_data, self.settings)
        optimizer.calculate_metrics()

        try:
            optimal_weights = optimizer.optimize_sharpe_ratio(
                risk_free_rate=risk_free_rate,
                weight_bounds=weight_bounds,
            )
        except Exception:
            logger.exception("Optimization failed")
            raise

        # --- 7. Calculate Advanced Metrics ---
        optimized_stats = optimizer.get_advanced_stats(optimal_weights)

        total_equity_value = sum(equity_holdings_optimized.values())
        current_weights = {
            k: v / total_equity_value for k, v in equity_holdings_optimized.items()
        }
        current_stats = optimizer.get_advanced_stats(current_weights)

        # --- 8. Allocate ---
        allocator = Allocator(
            equity_holdings_optimized, debt_capital, optimal_weights, months
        )
        transfers = allocator.calculate_transfers()
        summary = allocator.get_summary()

        # --- 9. Report ---
        reporter = Reporter(self.settings)
        report_path = reporter.generate_report(
            summary,
            optimal_weights,
            transfers,
            duration=months,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
            excluded_funds=excluded_funds,
        )

        return AdvisoryResult(
            optimal_weights=optimal_weights,
            transfers=transfers,
            summary=summary,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
            report_path=report_path,
            excluded_funds=excluded_funds,
            valid_funds=valid_funds,
            debt_capital=debt_capital,
            months=months,
        )

    # ------------------------------------------------------------------
    # Optimization only
    # ------------------------------------------------------------------

    def optimize_portfolio(
        self,
        nav_data: pd.DataFrame,
        risk_free_rate: float = 0.07,
        weight_bounds: tuple[float, float] = (0.0, 1.0),
    ) -> dict[str, float]:
        """Optimize portfolio weights for maximum Sharpe ratio.

        Args:
            nav_data: DataFrame with dates as index and fund names as columns.
            risk_free_rate: Risk-free rate (default 0.07 = 7%).
            weight_bounds: Tuple of (min_weight, max_weight) for each asset.

        Returns:
            Mapping of fund name to target weight.
        """
        optimizer = PortfolioOptimizer(nav_data, self.settings)
        optimizer.calculate_metrics()
        return optimizer.optimize_sharpe_ratio(
            risk_free_rate=risk_free_rate,
            weight_bounds=weight_bounds,
        )

    # ------------------------------------------------------------------
    # Allocation only
    # ------------------------------------------------------------------

    def calculate_allocations(
        self,
        current_holdings: dict[str, float],
        debt_capital: float,
        optimal_weights: dict[str, float],
        months: int,
    ) -> dict[str, float]:
        """Calculate monthly STP transfer amounts.

        Args:
            current_holdings: Mapping of fund name to current value (INR).
            debt_capital: Total debt capital available (INR).
            optimal_weights: Mapping of fund name to target weight (0.0 to 1.0).
            months: Number of months to deplete the debt capital.

        Returns:
            Mapping of fund name to monthly transfer amount (INR).
        """
        allocator = Allocator(
            current_holdings, debt_capital, optimal_weights, months
        )
        return allocator.calculate_transfers()

    # ------------------------------------------------------------------
    # Report only
    # ------------------------------------------------------------------

    def generate_report(
        self,
        allocator_summary: dict,
        optimal_weights: dict[str, float],
        transfers: dict[str, float],
        duration: int = 12,
        current_stats: dict | None = None,
        optimized_stats: dict | None = None,
    ) -> str:
        """Generate a Markdown rebalancing report.

        Args:
            allocator_summary: Summary dict from Allocator.get_summary().
            optimal_weights: Mapping of fund name to target weight.
            transfers: Mapping of fund name to monthly transfer amount.
            duration: Planning horizon in months (default 12).
            current_stats: Optional current portfolio stats dict.
            optimized_stats: Optional optimized portfolio stats dict.

        Returns:
            The file path of the generated report.
        """
        reporter = Reporter(self.settings)
        return reporter.generate_report(
            allocator_summary,
            optimal_weights,
            transfers,
            duration=duration,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
        )
