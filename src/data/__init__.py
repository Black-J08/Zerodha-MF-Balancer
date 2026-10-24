"""Data access layer for MF Balancer.

Provides NAV fetching, scheme code resolution, and portfolio holdings
access through the DataEngine class and supporting modules.
"""

from src.data.engine import DataEngine

__all__ = ["DataEngine"]
