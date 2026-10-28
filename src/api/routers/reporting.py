"""Reporting API routes.

Endpoints for generating and retrieving rebalancing reports.
"""

import logging
import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.dependencies import get_service
from src.services import PortfolioService

logger = logging.getLogger(__name__)

router = APIRouter()

ServiceDep = Annotated[PortfolioService, Depends(get_service)]


class ReportRequest(BaseModel):
    """Request model for report generation.

    Attributes:
        allocator_summary: Summary dict from Allocator.get_summary().
        optimal_weights: Mapping of fund name to target weight.
        transfers: Mapping of fund name to monthly transfer amount.
        duration: Planning horizon in months (default 12).
        current_stats: Optional current portfolio stats dict.
        optimized_stats: Optional optimized portfolio stats dict.
    """

    allocator_summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Allocator summary dict",
    )
    optimal_weights: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of fund name to target weight",
    )
    transfers: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of fund name to monthly transfer amount",
    )
    duration: int = Field(default=12, ge=1, description="Planning horizon in months")
    current_stats: dict[str, Any] | None = Field(
        default=None, description="Optional current portfolio stats"
    )
    optimized_stats: dict[str, Any] | None = Field(
        default=None, description="Optional optimized portfolio stats"
    )


class ReportResponse(BaseModel):
    """Response model for report generation.

    Attributes:
        report_path: Path to the generated Markdown report.
    """

    report_path: str


@router.post("/generate", response_model=ReportResponse)
async def generate_report(
    request: ReportRequest,
    service: ServiceDep,
) -> ReportResponse:
    """Generate a Markdown rebalancing report.

    Args:
        request: Report generation request.

    Returns:
        ReportResponse with the path to the generated report.
    """
    try:
        report_path = service.generate_report(
            allocator_summary=request.allocator_summary,
            optimal_weights=request.optimal_weights,
            transfers=request.transfers,
            duration=request.duration,
            current_stats=request.current_stats,
            optimized_stats=request.optimized_stats,
        )
        return ReportResponse(report_path=report_path)
    except Exception as exc:
        logger.exception("Report generation failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/list")
async def list_reports(
    service: ServiceDep,
) -> dict[str, Any]:
    """List available report files.

    Returns:
        Dict with list of report filenames.
    """
    try:
        reports_dir = service.settings.reports_dir
        if not os.path.isdir(reports_dir):
            return {"reports": []}

        files = sorted(
            f for f in os.listdir(reports_dir) if f.endswith(".md")
        )
        return {"reports": files, "count": len(files)}
    except Exception as exc:
        logger.exception("Failed to list reports")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
