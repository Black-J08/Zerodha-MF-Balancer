"""Configuration management for MF Balancer.

Centralizes paths, settings, and environment variable loading so that
hardcoded strings are eliminated from the rest of the codebase.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Application configuration.

    Attributes:
        data_dir: Directory for intermediate data exports (CSV files).
        output_dir: Directory for generated reports.
        reports_dir: Subdirectory of output_dir for report files.
        kite_api_key: Zerodha Kite Connect API key.
        kite_api_secret: Zerodha Kite Connect API secret.
        kite_access_token: Zerodha Kite Connect access token (optional).
        risk_free_rate: Risk-free rate for Sharpe ratio (default 0.07 = 7%).
    """

    data_dir: str
    output_dir: str
    reports_dir: str
    kite_api_key: str | None
    kite_api_secret: str | None
    kite_access_token: str | None
    risk_free_rate: float = 0.07

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables and defaults.

        Loads ``.env`` via :func:`python-dotenv.load_dotenv`, then reads
        ``KITE_API_KEY``, ``KITE_API_SECRET``, and ``KITE_ACCESS_TOKEN``.

        Returns:
            A populated :class:`Config` instance.

        Raises:
            ValueError: If required API credentials are missing.
        """
        load_dotenv()

        api_key = os.getenv("KITE_API_KEY")
        api_secret = os.getenv("KITE_API_SECRET")
        access_token = os.getenv("KITE_ACCESS_TOKEN")

        if not api_key or not api_secret:
            raise ValueError(
                "KITE_API_KEY and KITE_API_SECRET must be set in .env"
            )

        return cls(
            data_dir="data",
            output_dir="output",
            reports_dir="output/reports",
            kite_api_key=api_key,
            kite_api_secret=api_secret,
            kite_access_token=access_token,
        )
