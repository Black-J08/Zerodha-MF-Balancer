"""Allocation API routes.

Endpoints for calculating STP transfer amounts.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_service
from src.services import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter()

ServiceDep = Annotated[PortfolioService, Depends(get_service)]


class AllocationRequest(BaseModel):
    """Request model for STP transfer calculation.

    Attributes:
        current_holdings: Mapping of fund name to current value (INR).
        debt_capital: Total debt capital available (INR).
        optimal_weights: Mapping of fund name to target weight (0.0 to 1.0).
        months: Number of months to deplete the debt capital.
    """

    current_holdings: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of fund name to current value (INR)",
    )
    debt_capital: float = Field(ge=0, description="Total debt capital available (INR)")
    optimal_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of fund name to target weight (0.0 to 1.0)",
    )
    months: int = Field(default=12, ge=1, description="Number of months to deplete debt capital")


class AllocationResponse(BaseModel):
    """Response model for STP transfer calculation.

    Attributes:
        transfers: Mapping of fund name to monthly transfer amount (INR).
        monthly_budget: Total monthly budget available for transfers.
        total_monthly_outflow: Sum of all monthly transfers.
    """

    transfers: dict[str, float]
    monthly_budget: float
    total_monthly_outflow: float


@router.post("/transfers", response_model=AllocationResponse)
async def calculate_transfers(
    request: AllocationRequest,
    service: ServiceDep,
) -> AllocationResponse:
    """Calculate monthly STP transfer amounts from debt to equity funds.

    Args:
        request: Allocation request with holdings, debt capital, and weights.

    Returns:
        AllocationResponse with transfer amounts per fund.
    """
    try:
        transfers = service.calculate_allocations(
            current_holdings=request.current_holdings,
            debt_capital=request.debt_capital,
            optimal_weights=request.optimal_weights,
            months=request.months,
        )

        monthly_budget = request.debt_capital / request.months
        total_outflow = sum(transfers.values())

        return AllocationResponse(
            transfers=transfers,
            monthly_budget=monthly_budget,
            total_monthly_outflow=total_outflow,
        )
    except Exception as exc:
        logger.exception("Allocation calculation failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
