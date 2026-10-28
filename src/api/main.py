"""FastAPI application entry point for MF Balancer.

Creates the FastAPI app and includes all API routers.
"""

from fastapi import FastAPI

from src.api.routers import allocation, portfolio, reporting

app = FastAPI(
    title="MF Balancer API",
    description="Mutual Fund Portfolio Optimization and Rebalancing API",
    version="0.1.0",
)

app.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
app.include_router(allocation.router, prefix="/allocation", tags=["allocation"])
app.include_router(reporting.router, prefix="/reporting", tags=["reporting"])


@app.get("/")
async def root() -> dict:
    """Root endpoint returning API metadata."""
    return {
        "name": "MF Balancer API",
        "version": "0.1.0",
        "docs": "/docs",
    }
