"""Shared dependencies for the FastAPI application.

Provides dependency functions for settings and service instances.
"""

from functools import lru_cache

from src.core.settings import Settings
from src.services import PortfolioService


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings.from_env()


def get_service(settings: Settings) -> PortfolioService:
    """Return a PortfolioService instance for the given settings."""
    return PortfolioService(settings)
