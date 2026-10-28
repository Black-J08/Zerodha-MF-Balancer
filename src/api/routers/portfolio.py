"""Portfolio API routes.

Endpoints for fetching holdings and optimizing portfolio weights.
"""

import logging
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_service
from src.services import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter()

ServiceDep = Annotated[PortfolioService, Depends(get_service)]


class OptimizeRequest(BaseModel):
    """Request model for portfolio optimization.

    Attributes:
        nav_data: Dict of fund name to list of NAV values (aligned by index).
        risk_free_rate: Risk-free rate (default 0.07 = 7%).
        weight_bounds: Tuple of (min_weight, max_weight) for each asset.
    """

    nav_data: dict[str, list[float]] = Field(
        default_factory=dict,
        description="Dict of fund name to list of NAV values",
    )
    risk_free_rate: float = Field(default=0.07, ge=0, le=1)
    weight_bounds: list[float] = Field(
        default_factory=lambda: [0.0, 1.0],
        description="[min_weight, max_weight] for each asset",
    )


class OptimizeResponse(BaseModel):
    """Response model for portfolio optimization.

    Attributes:
        weights: Mapping of fund name to target weight (0.0 to 1.0).
        risk_free_rate: Risk-free rate used.
        weight_bounds: Weight bounds used.
    """

    weights: dict[str, float]
    risk_free_rate: float
    weight_bounds: list[float]


@router.get("/holdings")
async def get_holdings(
    service: ServiceDep,
) -> dict[str, Any]:
    """Fetch current mutual fund holdings from Zerodha.

    Returns:
        Dict with holdings data and fund count.
    """
    try:
        holdings_df = service.data_engine.get_portfolio_holdings()
        if holdings_df.empty:
            return {"holdings": [], "count": 0}

        holdings = holdings_df.to_dict(orient="records")
        return {"holdings": holdings, "count": len(holdings)}
    except Exception as exc:
        logger.exception("Failed to fetch holdings")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_portfolio(
    request: OptimizeRequest,
    service: ServiceDep,
) -> OptimizeResponse:
    """Optimize portfolio weights for maximum Sharpe ratio.

    Args:
        request: Optimization request with NAV data and parameters.

    Returns:
        OptimizeResponse with optimal weights and parameters.
    """
    try:
        nav_data = pd.DataFrame(request.nav_data)
        weight_bounds: tuple[float, float] = (
            request.weight_bounds[0],
            request.weight_bounds[1],
        )

        weights = service.optimize_portfolio(
            nav_data=nav_data,
            risk_free_rate=request.risk_free_rate,
            weight_bounds=weight_bounds,
        )

        return OptimizeResponse(
            weights=weights,
            risk_free_rate=request.risk_free_rate,
            weight_bounds=list(weight_bounds),
        )
    except Exception as exc:
        logger.exception("Optimization failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
