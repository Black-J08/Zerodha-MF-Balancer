"""Logging facade for MF Balancer.

Provides a centralized logging configuration following AGENTS.md standards:
- Uses the standard library ``logging`` module
- Lazy ``%``-formatting at call sites (never f-strings)
- ``exc_info=True`` always when logging exceptions
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name.

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    # Only configure once to avoid duplicate handlers on repeated calls
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False

    return logger
