"""Service layer for MF Balancer.

Provides the PortfolioService class that orchestrates domain modules
(data, optimization, allocation, reporting) without knowledge of
presentation layers (CLI, API, UI).
"""

from src.services.portfolio_service import PortfolioService

__all__ = ["PortfolioService"]
