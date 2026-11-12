"""PortfolioService: application layer orchestrating domain modules.

Orchestrates portfolio evaluation for both MPT-Optimal and master-fund-based
modes through a single mode-agnostic entry point:

  fetch holdings → (optionally exclude master fund) → resolve scheme codes
  → fetch NAV history → DataPreparation.clean → calculate expected returns
  & covariance → optimize weights → calculate current & optimized stats
  → calculate rebalancing transfers → generate report

Authentication is handled by the presentation layer (CLI/API) before
calling the service. The service assumes settings already contain
valid credentials.

The service has no knowledge of presentation layers (CLI, API, UI).
All user interaction (prompts, console output) is handled by the
presentation layer that calls this service.
"""

import os

import pandas as pd

from src.allocation import Allocator
from src.core.evaluation import EvaluationMode, EvaluationResult
from src.core.logging import get_logger
from src.core.models import FundExclusion
from src.core.settings import Settings
from src.data import DataEngine, DataPreparation
from src.optimization import PortfolioOptimizer
from src.reporting import Reporter

logger = get_logger(__name__)


class PortfolioService:
    """Orchestrates domain modules for portfolio evaluation operations.

    Args:
        settings: Application configuration.
        data_engine: Optional DataEngine instance (for testability/mocking).
            If not provided, one is created from settings.
    """

    _data_preparation: DataPreparation | None = None

    def __init__(self, settings: Settings, data_engine: DataEngine | None = None):
        self.settings = settings
        self.data_engine = data_engine or DataEngine(settings)
        self._data_preparation = None

    @property
    def data_preparation(self) -> DataPreparation:
        """Lazily-initialized DataPreparation instance."""
        prep = self._data_preparation
        if prep is None:
            prep = DataPreparation()
            self._data_preparation = prep
        return prep

    # ------------------------------------------------------------------
    # Full evaluation workflow (mode-agnostic)
    # ------------------------------------------------------------------

    def evaluate(
        self,
        mode: EvaluationMode,
        months: int,
        risk_free_rate: float,
        weight_bounds: tuple[float, float] = (0.0, 1.0),
        source_fund_name: str | None = None,
        total_capital: float | None = None,
    ) -> EvaluationResult:
        """Run the complete portfolio evaluation workflow.

        Args:
            mode: The :class:`EvaluationMode` to run.
            months: Planning horizon in months.
            risk_free_rate: Risk-free rate for Sharpe Ratio (decimal).
            weight_bounds: Tuple of (min_weight, max_weight) for each asset.
            source_fund_name: Name of the debt fund to use as capital source.
                Required for MASTER_FUND mode when total_capital is not given.
            total_capital: Total capital to use as the rebalancing basis.
                If None, derived from the mode (master fund value for
                MASTER_FUND, total portfolio value for MPT_OPTIMAL).

        Returns:
            EvaluationResult containing all computed outputs.

        Raises:
            ValueError: If no holdings are found, no valid NAV data is
                available, or MASTER_FUND mode lacks a source fund/capital.
        """
        # --- 1. Portfolio Fetching ---
        holdings_df = self.data_engine.get_portfolio_holdings()
        if holdings_df.empty:
            raise ValueError(
                "No Mutual Fund holdings found in this Zerodha account!"
            )
        current_holdings = dict(zip(holdings_df["tradingsymbol"], holdings_df["value"]))
        fund_isin_map = dict(zip(holdings_df["tradingsymbol"], holdings_df["isin"]))

        # --- 2. Determine holdings to optimize and capital basis ---
        if mode == EvaluationMode.MASTER_FUND:
            if source_fund_name is None and total_capital is None:
                raise ValueError(
                    "MASTER_FUND mode requires source_fund_name or total_capital."
                )
            if source_fund_name and source_fund_name not in current_holdings:
                raise ValueError(
                    f"Source fund '{source_fund_name}' not found in holdings."
                )

            equity_holdings = current_holdings.copy()
            if source_fund_name:
                equity_holdings.pop(source_fund_name, None)

            if total_capital is None:
                total_capital = current_holdings[source_fund_name]  # type: ignore[index]
        else:  # MPT_OPTIMAL
            equity_holdings = current_holdings.copy()
            if total_capital is None:
                total_capital = sum(current_holdings.values())

        # --- 3. Fetch Real NAVs ---
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

        if nav_data.empty:
            raise ValueError(
                "Could not fetch NAV data for ANY fund. Cannot optimize."
            )

        # --- 4. Data Preparation (normalization, validation, overlap cleaning) ---
        cleaned_prices, prep_exclusions = self.data_preparation.prepare(nav_data)
        excluded_funds.extend(prep_exclusions)

        valid_funds = cleaned_prices.columns.tolist()
        if not valid_funds:
            raise ValueError(
                "No valid funds remain after data preparation. Cannot optimize."
            )

        # Save Cleaned NAV Data for Inspection
        nav_export_path = os.path.join(self.settings.data_dir, "nav_history.csv")
        os.makedirs(os.path.dirname(nav_export_path), exist_ok=True)
        cleaned_prices.to_csv(nav_export_path)
        logger.info("Saved historical NAV data to %s", nav_export_path)

        holdings_optimized = {
            k: v for k, v in equity_holdings.items() if k in valid_funds
        }

        # --- 5. Optimize ---
        optimizer = PortfolioOptimizer(cleaned_prices, self.settings)
        optimizer.calculate_metrics()

        try:
            optimal_weights = optimizer.optimize_sharpe_ratio(
                risk_free_rate=risk_free_rate,
                weight_bounds=weight_bounds,
            )
        except Exception:
            logger.exception("Optimization failed")
            raise

        # --- 6. Calculate Advanced Metrics ---
        optimized_stats = optimizer.get_advanced_stats(optimal_weights)

        total_equity_value = sum(holdings_optimized.values())
        current_weights = {
            k: v / total_equity_value for k, v in holdings_optimized.items()
        }
        current_stats = optimizer.get_advanced_stats(current_weights)

        # --- 7. Allocate ---
        allocator = Allocator(
            holdings_optimized, total_capital, optimal_weights, months
        )
        transfers = allocator.calculate_transfers()
        summary = allocator.get_summary()

        # --- 8. Report ---
        reporter = Reporter(self.settings)
        report_path = reporter.generate_report(
            summary,
            optimal_weights,
            transfers,
            duration=months,
            current_stats=current_stats,
            optimized_stats=optimized_stats,
            excluded_funds=excluded_funds,
            mode=mode,
        )

        return EvaluationResult(
            mode=mode,
            weights=optimal_weights,
            current_weights=current_weights,
            optimized_stats=optimized_stats,
            current_stats=current_stats,
            transfers=transfers,
            summary=summary,
            report_path=report_path,
            excluded_funds=excluded_funds,
            valid_funds=valid_funds,
            total_capital=total_capital,
            months=months,
        )
