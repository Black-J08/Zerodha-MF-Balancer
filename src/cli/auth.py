"""Authentication flow for Zerodha Kite Connect.

Handles login, session verification, and token persistence.
"""

import typer
from kiteconnect import KiteConnect
from rich.console import Console
from rich.prompt import Prompt

from src.core.config import Config
from src.core.logging import get_logger

logger = get_logger(__name__)
console = Console()


def authenticate(config: Config) -> KiteConnect:
    """Authenticate with Zerodha Kite Connect.

    Verifies the existing access token, or initiates the interactive
    login flow if the session is expired or missing.

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
        print(f"\n1. Open this URL in your browser:\n{kite.login_url()}")
        print("\n2. After login, you will be redirected to a URL (e.g., https://127.0.0.1/?request_token=...)\n")
        request_token = Prompt.ask("3. Paste the 'request_token' value here").strip()

        try:
            data = kite.generate_session(request_token, api_secret=config.kite_api_secret)
            access_token = data["access_token"]
            kite.set_access_token(access_token)

            # Persist the new access token to .env
            with open(".env", "a") as f:
                f.write(f"\nKITE_ACCESS_TOKEN={access_token}\n")
            console.print("[green]New Access Token saved.[/green]")
            return kite
        except Exception as e:
            logger.exception("Login failed")
            console.print(f"[bold red]Login Failed: {e}[/bold red]")
            raise typer.Exit(code=1)
