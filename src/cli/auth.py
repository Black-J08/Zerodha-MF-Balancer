"""Authentication flow for Zerodha Kite Connect.

Handles login, session verification, and token persistence.
"""

import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import typer
from dotenv import set_key
from kiteconnect import KiteConnect
from rich.console import Console
from rich.prompt import Prompt

from src.cli.callback_server import CallbackServer
from src.core.logging import get_logger
from src.core.settings import Settings

logger = get_logger(__name__)
console = Console()


def _extract_request_token(value: str) -> str | None:
    """Extract ``request_token`` from a bare token or a full redirect URL.

    Args:
        value: Either a bare ``request_token`` string or a full redirect
            URL containing a ``request_token`` query parameter.

    Returns:
        The extracted ``request_token``, or None if it cannot be found.
    """
    value = value.strip()
    if not value:
        return None

    # If it looks like a URL, parse the query string for request_token.
    if "://" in value or value.startswith(("/?", "/")):
        parsed = urlparse(value)
        tokens = parse_qs(parsed.query).get("request_token")
        if tokens:
            return tokens[0]
        # URL-like input but no request_token found.
        return None

    # Otherwise treat it as a bare request_token.
    return value


def _persist_token(config: Settings, access_token: str) -> None:
    """Persist the access token to the appropriate .env file.

    Writes to the .env that was loaded (CWD or project root), otherwise
    creates a new .env in CWD. Also updates ``os.environ`` and
    ``config.kite_access_token`` so the new token is immediately available
    to the current session and to any subsequently created :class:`Settings`
    instance. Without this, ``load_dotenv(override=False)`` would keep a
    stale ``KITE_ACCESS_TOKEN`` from ``os.environ`` on the next run, causing
    repeated ``TokenException`` errors and login prompts.
    """
    if config.env_loaded and config.env_path:
        token_env_path = Path(config.env_path)
    else:
        token_env_path = Path.cwd() / ".env"
    set_key(token_env_path, "KITE_ACCESS_TOKEN", access_token, quote_mode="never")
    # Update os.environ so the new token is visible to future Settings
    # instances (load_dotenv(override=False) won't override an existing
    # KITE_ACCESS_TOKEN from os.environ).
    os.environ["KITE_ACCESS_TOKEN"] = access_token
    # Update the current config so the live kite client uses the new token.
    config.kite_access_token = access_token
    console.print("[green]New Access Token saved.[/green]")


def _complete_session(kite: KiteConnect, request_token: str, config: Settings) -> KiteConnect:
    """Generate a session from the request token and persist the access token.

    Args:
        kite: The KiteConnect client instance.
        request_token: The request token obtained from the redirect.
        config: Application configuration with API credentials.

    Returns:
        An authenticated :class:`kiteconnect.KiteConnect` instance.

    Raises:
        typer.Exit: If session generation fails.
    """
    try:
        data = kite.generate_session(request_token, api_secret=config.kite_api_secret)
        access_token = data["access_token"]
        kite.set_access_token(access_token)
        _persist_token(config, access_token)
        return kite
    except Exception as e:
        logger.exception("Login failed")
        console.print(f"[bold red]Login Failed: {e}[/bold red]")
        raise typer.Exit(code=1)


def authenticate(config: Settings) -> KiteConnect:
    """Authenticate with Zerodha Kite Connect.

    Verifies the existing access token, or initiates the interactive
    login flow if the session is expired or missing.

    The login flow uses a lightweight callback server (derived from
    ``KITE_REDIRECT_URL``) to automatically capture the ``request_token``
    from Zerodha's redirect. If the callback server cannot start or times
    out, it falls back to the manual ``Prompt.ask`` flow.

    Args:
        config: Application configuration with API credentials.

    Returns:
        An authenticated :class:`kiteconnect.KiteConnect` instance.

    Raises:
        typer.Exit: If authentication fails.
    """
    kite = KiteConnect(api_key=config.kite_api_key)

    if config.kite_access_token:
        kite.set_access_token(config.kite_access_token)

    try:
        with console.status("[bold green]Verifying Zerodha Session..."):
            kite.profile()
        return kite
    except Exception:
        logger.exception("Session verification failed")
        console.print("[yellow]Session expired or invalid. Initiating Login Flow...[/yellow]")

    # --- Primary flow: automatic request_token capture via callback server ---
    if config.kite_redirect_url:
        console.print(
            f"\n[bold cyan]Starting automatic login flow via callback server[/bold cyan]\n"
            f"Callback URL: [bold]{config.kite_redirect_url}[/bold]\n"
            f"Make sure this redirect URL is configured in your Zerodha developer console.\n"
        )
        try:
            server = CallbackServer(config)
            server.start()
            console.print(f"\n1. Open this URL in your browser:\n{kite.login_url()}")
            console.print(
                f"\n2. After login, Zerodha will redirect to {config.kite_redirect_url}\n"
                f"   and the request_token will be captured automatically.\n"
            )
            request_token = server.wait_for_token(timeout=120.0)
            if request_token:
                console.print("[green]Request token captured automatically.[/green]")
                return _complete_session(kite, request_token, config)
            console.print(
                "[yellow]Callback server did not capture a token. Falling back to manual entry.[/yellow]"
            )
        except OSError as e:
            logger.warning("Callback server failed to start: %s", e)
            console.print(
                f"[yellow]Callback server unavailable ({e}). Falling back to manual entry.[/yellow]"
            )
        except Exception:
            logger.exception("Callback server error")
            console.print(
                "[yellow]Callback server error. Falling back to manual entry.[/yellow]"
            )

    # --- Fallback flow: manual request_token entry ---
    print(f"\n1. Open this URL in your browser:\n{kite.login_url()}")
    print("\n2. After login, you will be redirected to a URL (e.g., https://127.0.0.1/?request_token=...)\n")
    raw = Prompt.ask("3. Paste the 'request_token' or the full redirect URL here").strip()
    request_token = _extract_request_token(raw)
    if not request_token:
        console.print("[bold red]Login Failed: No request_token provided.[/bold red]")
        raise typer.Exit(code=1)

    return _complete_session(kite, request_token, config)
