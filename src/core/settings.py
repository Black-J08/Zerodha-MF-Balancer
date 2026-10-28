"""Configuration management for MF Balancer.

Centralizes paths, settings, and environment variable loading with type
validation. Preserves the existing configuration-loading priority:

1. ``.env`` in CWD (where ``mf-balancer`` is run) — takes precedence
2. Skip ``.env`` loading if ``KITE_API_KEY`` and ``KITE_API_SECRET`` already
   in ``os.environ``
3. ``.env`` in project root
4. Raise :exc:`ValueError` if required vars still missing
"""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


def _resolve_project_root() -> Path | None:
    """Resolve the project root directory.

    Priority:
    1. MF_BALANCER_HOME environment variable
    2. Derived from __file__ (src/core/settings.py -> parents[2])
    3. Upward search from CWD for .env or pyproject.toml
    4. Fallback to CWD

    Returns:
        The resolved project root path, or None if it cannot be determined.
    """
    # 1. Explicit override via environment variable
    override = os.getenv("MF_BALANCER_HOME")
    if override:
        return Path(override).resolve()

    # 2. Derived from source file location (editable/dev installs)
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / ".env").exists() or (source_root / "pyproject.toml").exists():
        return source_root

    # 3. Upward search from CWD for .env or pyproject.toml
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        if (parent / ".env").exists() or (parent / "pyproject.toml").exists():
            return parent

    # 4. Fallback to CWD
    return cwd


PROJECT_ROOT = _resolve_project_root()


def _is_inside_site_packages_or_venv(path: Path) -> bool:
    """Check if a path is inside a site-packages directory or virtual environment.

    Args:
        path: The path to check.

    Returns:
        True if the path is inside site-packages or a venv, False otherwise.
    """
    resolved = path.resolve()
    for parent in [resolved, *resolved.parents]:
        if parent.name == "site-packages":
            return True
        if (parent / "pyvenv.cfg").exists():
            return True
    return False


def _resolve_env_path() -> Path | None:
    """Resolve the .env file path based on loading priority.

    Priority:
    1. .env in CWD (where mf-balancer is run)
    2. Skip if KITE_API_KEY and KITE_API_SECRET already in os.environ
    3. .env in project root
    4. None (no .env found)

    Returns:
        Path to the .env file to load, or None if no .env should be loaded.
    """
    # Priority 1: .env in CWD
    cwd_env = Path.cwd() / ".env"
    if cwd_env.exists():
        return cwd_env

    # Priority 2: Skip if credentials already in environment
    if os.getenv("KITE_API_KEY") and os.getenv("KITE_API_SECRET"):
        return None

    # Priority 3: .env in project root
    if PROJECT_ROOT is not None:
        project_root_env = PROJECT_ROOT / ".env"
        if project_root_env.exists():
            return project_root_env

    # Priority 4: No .env found
    return None


def _resolve_data_dir(env_dir: Path | None) -> Path:
    """Resolve the data directory, ensuring it never lands inside site-packages or venv.

    Args:
        env_dir: The directory where .env was loaded from, or None.

    Returns:
        A safe absolute path for the data directory.
    """
    if env_dir is None:
        return Path.cwd() / "output" / "data"

    candidate = env_dir / "data"
    if _is_inside_site_packages_or_venv(candidate):
        return Path.cwd() / "output" / "data"

    return candidate


@dataclass
class Settings:
    """Application configuration.

    Attributes:
        data_dir: Directory for intermediate data exports (CSV files).
        output_dir: Directory for generated reports.
        reports_dir: Subdirectory of output_dir for report files.
        kite_api_key: Zerodha Kite Connect API key.
        kite_api_secret: Zerodha Kite Connect API secret.
        kite_access_token: Zerodha Kite Connect access token (optional).
        kite_redirect_url: Zerodha Kite Connect redirect URL (optional).
            Used to derive the callback server host, port, and path for
            automatic request_token capture.
        risk_free_rate: Risk-free rate for Sharpe ratio (default 0.07 = 7%).
        env_loaded: Whether a .env file was loaded.
        env_path: Path to the .env file that was loaded, if any.
    """

    kite_api_key: str | None = None
    kite_api_secret: str | None = None
    kite_access_token: str | None = None
    kite_redirect_url: str | None = None
    risk_free_rate: float = 0.07
    data_dir: str = ""
    output_dir: str = ""
    reports_dir: str = ""
    env_loaded: bool = False
    env_path: str | None = None

    def __post_init__(self) -> None:
        """Load configuration from environment variables and .env file.

        Follows .env loading priority:
        1. .env in CWD (where mf-balancer is run)
        2. Skip if KITE_API_KEY and KITE_API_SECRET already in os.environ
        3. .env in project root
        4. Raise ValueError if required vars still missing
        """
        env_path = _resolve_env_path()
        env_loaded = env_path is not None

        # Load .env file if one was resolved (override=False so existing
        # environment variables take precedence over .env values)
        if env_path:
            load_dotenv(env_path, override=False)

        # Read credentials from environment (os.environ now includes .env
        # values loaded above, with pre-existing env vars taking precedence)
        self.kite_api_key = os.getenv("KITE_API_KEY")
        self.kite_api_secret = os.getenv("KITE_API_SECRET")
        self.kite_access_token = os.getenv("KITE_ACCESS_TOKEN")
        self.kite_redirect_url = os.getenv("KITE_REDIRECT_URL")

        self.env_loaded = env_loaded
        self.env_path = str(env_path) if env_path else None

        env_dir = Path(env_path).parent if env_path else None
        self.data_dir = str(_resolve_data_dir(env_dir))
        self.output_dir = str(Path.cwd() / "output")
        self.reports_dir = str(Path.cwd() / "output" / "reports")

        self._check_credentials()
        self._validate_redirect_url()

    def _check_credentials(self) -> None:
        """Validate that required API credentials are present."""
        if not self.kite_api_key or not self.kite_api_secret:
            raise ValueError(
                "KITE_API_KEY and KITE_API_SECRET must be set in .env "
                "or exported as environment variables"
            )

    def _validate_redirect_url(self) -> None:
        """Validate the redirect URL if provided.

        The redirect URL must have an http/https scheme, a hostname, an
        explicit port, and a path (which may be just "/"). The URL is used
        exactly as configured; no default port or other component is added.

        Raises:
            ValueError: If the redirect URL is present but invalid.
        """
        if not self.kite_redirect_url:
            return

        parsed = urlparse(self.kite_redirect_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"KITE_REDIRECT_URL must use http or https scheme, got: "
                f"{self.kite_redirect_url!r}"
            )
        if not parsed.hostname:
            raise ValueError(
                f"KITE_REDIRECT_URL must include a hostname, got: "
                f"{self.kite_redirect_url!r}"
            )
        if parsed.port is None:
            raise ValueError(
                f"KITE_REDIRECT_URL must include an explicit port, got: "
                f"{self.kite_redirect_url!r}"
            )
        if not parsed.path:
            raise ValueError(
                f"KITE_REDIRECT_URL must include a path, got: "
                f"{self.kite_redirect_url!r}"
            )

    @property
    def kite_callback_host(self) -> str | None:
        """Return the callback host derived from the redirect URL."""
        if not self.kite_redirect_url:
            return None
        return urlparse(self.kite_redirect_url).hostname

    @property
    def kite_callback_port(self) -> int | None:
        """Return the callback port derived from the redirect URL.

        Returns the port exactly as configured in the URL, or None if no
        port is specified. No default port is added.
        """
        if not self.kite_redirect_url:
            return None
        return urlparse(self.kite_redirect_url).port

    @property
    def kite_callback_path(self) -> str:
        """Return the callback path derived from the redirect URL."""
        if not self.kite_redirect_url:
            return "/callback"
        parsed = urlparse(self.kite_redirect_url)
        return parsed.path or "/callback"

    @classmethod
    def from_env(cls) -> "Settings":
        """Load configuration from environment variables and defaults.

        Follows .env loading priority:
        1. .env in CWD (where mf-balancer is run)
        2. Skip if KITE_API_KEY and KITE_API_SECRET already in os.environ
        3. .env in project root
        4. Raise ValueError if required vars still missing

        Returns:
            A populated :class:`Settings` instance.

        Raises:
            ValueError: If required API credentials are missing after all attempts.
        """
        return cls()
