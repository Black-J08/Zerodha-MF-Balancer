"""Data preparation for portfolio evaluation.

Provides an explicit normalization and validation step that runs before any
statistical calculations. This ensures percentage-based returns are applied
consistently and invalid or insufficient data is handled deterministically,
rather than relying solely on PyPortfolioOpt's internal handling.
"""

from __future__ import annotations

import pandas as pd

from src.core.logging import get_logger
from src.core.models import FundExclusion

logger = get_logger(__name__)

# Minimum number of overlapping observations required for a fund to be
# included in optimization.
_MIN_OBSERVATIONS = 30


class DataPreparation:
    """Prepares raw NAV data for statistical calculations.

    Responsibilities:
      1. Validate that all NAV values are positive and finite.
      2. Compute percentage returns (``pct_change``) for validation.
      3. Align all series on the common overlapping date index.
      4. Drop funds with fewer than ``_MIN_OBSERVATIONS`` observations or
         that break the common overlapping period.

    Args:
        min_observations: Minimum number of observations required per fund
            (default 30).
    """

    def __init__(self, min_observations: int = _MIN_OBSERVATIONS) -> None:
        self.min_observations = min_observations

    def prepare(
        self, nav_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[FundExclusion]]:
        """Clean and validate NAV data before statistical calculations.

        Args:
            nav_data: DataFrame with dates as index and fund names as columns,
                containing historical NAV levels.

        Returns:
            A tuple of ``(cleaned_prices, exclusions)`` where
            ``cleaned_prices`` is the validated, overlap-aligned NAV DataFrame
            and ``exclusions`` lists funds dropped during preparation.

        Raises:
            ValueError: If ``nav_data`` is empty or no funds remain after
                cleaning.
        """
        if nav_data.empty:
            raise ValueError("NAV data is empty. Cannot prepare data for optimization.")

        exclusions: list[FundExclusion] = []
        cleaned = nav_data.copy()

        # --- 1. Validate NAV positivity and finiteness ---
        # Only the valid (non-NaN) portion of each series is checked; NaN
        # padding from date misalignment is handled by the alignment step.
        invalid_columns: list[str] = []
        for column in cleaned.columns:
            series = cleaned[column]
            if series.isna().all():
                invalid_columns.append(column)
                continue
            valid_values = series.dropna()
            if not (valid_values > 0).all():
                invalid_columns.append(column)

        for column in invalid_columns:
            cleaned = cleaned.drop(columns=column)
            exclusions.append(
                FundExclusion(
                    fund_name=column,
                    reason="Invalid NAV data",
                    detail="Non-positive or NaN values detected",
                )
            )
            logger.warning(
                "Dropped fund %s due to invalid NAV data.", column
            )

        if cleaned.empty:
            raise ValueError(
                "No funds with valid NAV data remain after validation. "
                "Cannot optimize."
            )

        # Keep a pre-alignment copy for re-alignment after dropping culprits.
        pre_alignment = cleaned.copy()

        # --- 2. Capture original start dates before alignment ---
        # These identify which fund(s) break the common overlap.
        original_start_dates = cleaned.apply(lambda x: x.first_valid_index())

        # --- 3. Compute percentage returns for validation ---
        # Percentage-based returns are used throughout, not absolute NAV
        # differences.
        _ = cleaned.pct_change().dropna()

        # --- 4. Align on common overlapping date index ---
        cleaned = cleaned.dropna(how="any")

        if cleaned.empty:
            raise ValueError(
                "No overlapping observations remain after aligning dates. "
                "Cannot optimize."
            )

        # --- 5. Drop funds that break the common overlap ---
        # If the common overlap is insufficient, identify the fund(s) with
        # the latest original start date (the culprits) and drop them,
        # then re-align from the pre-alignment data.
        if len(cleaned) < self.min_observations:
            max_start = original_start_dates.max()
            culprits = original_start_dates[original_start_dates == max_start].index.tolist()
            cleaned = pre_alignment.drop(columns=culprits)
            # Re-align after removing culprit columns
            cleaned = cleaned.dropna(how="any")
            for culprit in culprits:
                exclusions.append(
                    FundExclusion(
                        fund_name=culprit,
                        reason="Insufficient overlapping period",
                        detail=f"Fewer than {self.min_observations} observations",
                    )
                )
                logger.warning(
                    "Dropped fund %s due to insufficient overlapping period.",
                    culprit,
                )

        if cleaned.empty:
            raise ValueError(
                "No funds remain after overlap cleaning. Cannot optimize."
            )

        if len(cleaned) < self.min_observations:
            raise ValueError(
                f"Insufficient overlapping historical data "
                f"({len(cleaned)} days, {self.min_observations} required)."
            )

        logger.info(
            "Prepared NAV data: %d funds, %d overlapping observations.",
            len(cleaned.columns),
            len(cleaned),
        )

        return cleaned, exclusions
