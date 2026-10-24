"""Capital allocation layer for MF Balancer.

Provides the Allocator class for computing STP (Systematic Transfer Plan)
transfer amounts using Target Duration Convergence.
"""

from src.allocation.allocator import Allocator

__all__ = ["Allocator"]
