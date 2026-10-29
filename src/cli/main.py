"""CLI entry point for MF Balancer.

Typer-based command-line interface that handles user interaction and
delegates orchestration to PortfolioService.
"""

import typer
from rich.console import Console
from rich.prompt import FloatPrompt, IntPrompt
from rich.table import Table

from src.cli.auth import authenticate
from src.core.logging import get_logger
from src.core.settings import Settings
from src.data import DataEngine
from src.services import PortfolioService

logger = get_logger(__name__)
console = Console()

app = typer.Typer()


@app.command()
def advise(
    debt_capital: float | None = typer.Option(
        None, help="Total capital available in Debt Fund (Optional if selecting from portfolio)"
    ),
    months: int = typer.Option(12, help="Number of months to deplete the debt capital"),
    risk_factor: float = typer.Option(0.07, help="Risk free rate for Sharpe Ratio (decimal)"),
) -> None:
    """Run the Mutual Fund Balancer in Advisory Mode."""
    config = Settings.from_env()

    # --- 1. Authentication ---
    kite = authenticate(config)

    # --- 2. Portfolio Fetching (for interactive source fund selection) ---
    de = DataEngine(config, kite=kite)

    with console.status("[bold green]Fetching Portfolio Holdings..."):
        holdings_df = de.get_portfolio_holdings()
        if holdings_df.empty:
            console.print("[red]No Mutual Fund holdings found in this Zerodha account![/red]")
            raise typer.Exit()
        current_holdings = dict(zip(holdings_df["tradingsymbol"], holdings_df["value"]))

    # --- 3. Select Source Debt Fund ---
    source_fund_name: str | None = None
    if debt_capital is None:
        console.print("\n[bold cyan]Select your 'Master Debt Fund' (Source of Capital):[/bold cyan]")
        funds = list(current_holdings.keys())

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Fund Name")
        table.add_column("Current Value", justify="right")

        for idx, fund in enumerate(funds):
            table.add_row(str(idx + 1), fund, f"₹{current_holdings[fund]:,.2f}")
        console.print(table)

        choice = IntPrompt.ask(f"Enter ID of the Debt Fund (1-{len(funds)})")
        if 1 <= choice <= len(funds):
            source_fund_name = funds[choice - 1]
            debt_capital = current_holdings[source_fund_name]
            console.print(
                f"[green]Selected Source:[/green] {source_fund_name} (₹{debt_capital:,.2f})"
            )
        else:
            console.print("[red]Invalid selection![/red]")
            raise typer.Exit(code=1)

    # --- 4. Optimization Strategy Selection ---
    console.print("\n[bold cyan]Select Optimization Strategy:[/bold cyan]")
    console.print("1. [bold]Maximum Sharpe Ratio[/bold] (Standard, Unconstrained)")
    console.print("   [dim]- Finds the mathematically optimal portfolio.[/dim]")
    console.print("   [dim]- May result in 0% allocation to many funds (Concentrated).[/dim]")

    console.print("2. [bold]Constrained Optimization[/bold] (Diversified)")
    console.print("   [dim]- Finds the best portfolio considering your limits.[/dim]")
    console.print("   [dim]- Forces diversification (e.g., 'Don't put more than 20% in any fund').[/dim]")

    strategy_choice = IntPrompt.ask("Enter Choice", choices=["1", "2"], default=1)

    weight_bounds: tuple[float, float] = (0.0, 1.0)  # Default: 0% to 100%

    if strategy_choice == 2:
        console.print("\n[bold]Configure Constraints:[/bold]")
        max_w = FloatPrompt.ask(
            "Enter Maximum weight per fund (e.g., 0.20 for 20%)", default=1.0
        )
        min_w = FloatPrompt.ask(
            "Enter Minimum weight per fund (e.g., 0.05 for 5%)", default=0.00
        )

        # Validation
        valid_funds_count = len(current_holdings) - (1 if source_fund_name else 0)
        if min_w * valid_funds_count > 1.0:
            console.print(
                f"[bold red]Error:[/bold red] Minimum weight of {min_w:.0%} for {valid_funds_count} funds requires {min_w * valid_funds_count:.0%} allocation, which is > 100%."
            )
            raise typer.Exit(code=1)

        weight_bounds = (min_w, max_w)
        console.print(f"[green]Applying Constraints: Min {min_w:.0%} | Max {max_w:.0%}[/green]")

    # --- 5. Delegate to PortfolioService ---
    service = PortfolioService(config, data_engine=de)

    with console.status("[bold blue]Running portfolio advisory..."):
        try:
            result = service.run_advisory(
                debt_capital=debt_capital,
                months=months,
                risk_free_rate=risk_factor,
                source_fund_name=source_fund_name,
                weight_bounds=weight_bounds,
            )
        except ValueError as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(code=1)
        except Exception:
            logger.exception("Advisory workflow failed")
            console.print("[bold red]Advisory workflow failed.[/bold red]")
            raise typer.Exit(code=1)

    # --- 6. Display Results ---
    console.print("\n[bold]Optimal Equity Allocation:[/bold]")
    for f, w in result.optimal_weights.items():
        console.print(f"- {f}: {w * 100:.1f}%")

    console.print("\n[bold]Portfolio Health Check:[/bold]")
    current_sharpe = result.current_stats["Sharpe Ratio"] if result.current_stats else 0.0
    optimized_sharpe = result.optimized_stats["Sharpe Ratio"] if result.optimized_stats else 0.0
    console.print(
        f"Current Sharpe: {current_sharpe:.2f} | "
        f"Optimized Sharpe: {optimized_sharpe:.2f}"
    )

    if result.excluded_funds:
        table = Table(
            title="[yellow]Excluded Funds[/yellow]",
            show_header=True,
            header_style="bold yellow",
        )
        table.add_column("Fund Name", style="dim")
        table.add_column("Reason")
        table.add_column("Detail")
        for exclusion in result.excluded_funds:
            table.add_row(
                exclusion.fund_name,
                exclusion.reason,
                exclusion.detail or "",
            )
        console.print("\n")
        console.print(table)

    console.print(f"\n[bold green]Success![/bold green] Report saved to: [link={result.report_path}]{result.report_path}[/link]")
