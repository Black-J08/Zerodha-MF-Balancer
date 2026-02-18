import os
import typer
from dotenv import load_dotenv
from mf_balancer.src.data_engine import DataEngine
from mf_balancer.src.optimizer import PortfolioOptimizer
from mf_balancer.src.allocator import Allocator
from mf_balancer.src.reporter import Reporter
from kiteconnect import KiteConnect
import pandas as pd
from datetime import datetime
from rich.console import Console
from rich.prompt import IntPrompt, FloatPrompt

app = typer.Typer()
console = Console()

@app.command()
def advise(
    debt_capital: float = typer.Option(None, help="Total capital available in Debt Fund (Optional if selecting from portfolio)"),
    months: int = typer.Option(12, help="Number of months to deplete the debt capital"),
    risk_factor: float = typer.Option(0.07, help="Risk free rate for Sharpe Ratio (decimal)")
):
    """
    Run the Mutual Fund Balancer in Advisory Mode.
    """
    load_dotenv()
    
    # --- 1. Authentication ---
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")
    access_token = os.getenv("KITE_ACCESS_TOKEN")
    
    if not api_key or not api_secret:
        console.print("[bold red]Error: KITE_API_KEY and KITE_API_SECRET must be set in .env[/bold red]")
        raise typer.Exit(code=1)

    # Interactive Auth Flow
    kite = KiteConnect(api_key=api_key)
    if access_token:
        kite.set_access_token(access_token)
        
    try:
        with console.status("[bold green]Verifying Zerodha Session..."):
            kite.profile()
    except Exception:
        console.print("[yellow]Session expired or invalid. Initiating Login Flow...[/yellow]")
        print(f"\n1. Open this URL in your browser:\n{kite.login_url()}")
        print("\n2. After login, you will be redirected to a URL (e.g., https://127.0.0.1/?request_token=...)\n")
        request_token = typer.prompt("3. Paste the 'request_token' value here").strip()
        
        try:
            data = kite.generate_session(request_token, api_secret=api_secret)
            access_token = data["access_token"]
            kite.set_access_token(access_token)
            with open(".env", "a") as f:
                f.write(f"\nKITE_ACCESS_TOKEN={access_token}\n")
            console.print(f"[green]New Access Token saved.[/green]")
        except Exception as e:
            console.print(f"[bold red]Login Failed: {e}[/bold red]")
            raise typer.Exit(code=1)

    de = DataEngine(api_key, access_token)
    
    # --- 2. Portfolio Fetching ---
    with console.status("[bold green]Fetching Portfolio Holdings..."):
        holdings_df = de.get_portfolio_holdings()
        if holdings_df.empty:
            console.print("[red]No Mutual Fund holdings found in this Zerodha account![/red]")
            raise typer.Exit()
        current_holdings = dict(zip(holdings_df['tradingsymbol'], holdings_df['value']))

    # --- 3. Select Source Debt Fund ---
    source_fund_name = None
    if debt_capital is None:
        console.print("\n[bold cyan]Select your 'Master Debt Fund' (Source of Capital):[/bold cyan]")
        funds = list(current_holdings.keys())
        
        import rich.table
        table = rich.table.Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="dim", width=4)
        table.add_column("Fund Name")
        table.add_column("Current Value", justify="right")
        
        for idx, fund in enumerate(funds):
            table.add_row(str(idx+1), fund, f"₹{current_holdings[fund]:,.2f}")
        console.print(table)
        
        choice = typer.prompt(f"Enter ID of the Debt Fund (1-{len(funds)})", type=int)
        if 1 <= choice <= len(funds):
            source_fund_name = funds[choice-1]
            debt_capital = current_holdings[source_fund_name]
            console.print(f"[green]Selected Source:[/green] {source_fund_name} (₹{debt_capital:,.2f})")
        else:
            console.print("[red]Invalid selection![/red]")
            raise typer.Exit(code=1)

    # --- 4. Prepare Optimization Data (Exclude Debt Fund) ---
    equity_holdings = current_holdings.copy()
    if source_fund_name:
        del equity_holdings[source_fund_name] 
        
    # --- 5. Fetch Real NAVs ---
    nav_data = pd.DataFrame()
    with console.status("[bold green]Fetching Historical NAVs for Equity Funds..."):
        for fund_name in equity_holdings.keys():
            console.print(f"Resolving Scheme Code for: [cyan]{fund_name}[/cyan]...")
            code = de.get_scheme_code_for_fund(fund_name)
            
            if code:
                try:
                    nav_series = de.get_historical_nav(code)
                    if nav_series.empty:
                        console.print(f"  [yellow]Warning[/yellow]: No data returned for {fund_name} (Code: {code}). Skipping.")
                        continue
                        
                    if len(nav_series) < 30:
                        console.print(f"  [yellow]Warning[/yellow]: insufficient history ({len(nav_series)} days) for {fund_name}. Need >30. Skipping.")
                        continue
                        
                    nav_data[fund_name] = nav_series
                    console.print(f"  [green]Found[/green] {len(nav_series)} records (Code: {code})")
                except Exception as e:
                     console.print(f"  [red]Failed to fetch NAV[/red]: {e}")
            else:
                console.print(f"  [red]Could not map fund name to AMFI Code automatically.[/red] Skipping.")

    # Remove funds for which we couldn't get NAVs
    valid_funds = nav_data.columns.tolist()
    if not valid_funds:
        console.print("[bold red]Critical Error:[/bold red] Could not fetch NAV data for ANY equity fund. Cannot optimize.")
        raise typer.Exit(code=1)
    
    # Pre-Optimization Data Cleaning
    # If we have NaNs (different start dates), we need to find a common subset.
    # If distinct sets of funds have NO overlap, dropna() will result in empty DF.
    
    # Strategy: Iteratively drop the fund that causes the most data loss until we have a valid set?
    # Simple Heuristic: strict dropna(). If empty, warn and exit or try to save it.
    
    current_len = len(nav_data.dropna())
    if current_len < 30:
        console.print(f"[yellow]Warning: Common overlapping period is too short ({current_len} days).[/yellow]")
        console.print("[yellow]Attempting to identify and remove funds with short history to save the optimization...[/yellow]")
        
        # Calculate start dates
        start_dates = nav_data.apply(lambda x: x.first_valid_index())
        max_start = start_dates.max() # The latest start date causes the cut
        
        # Identify funds starting at this max date
        culprits = start_dates[start_dates == max_start].index.tolist()
        console.print(f"Excluding recent funds causing history truncation: {culprits}")
        
        nav_data = nav_data.drop(columns=culprits)
        valid_funds = nav_data.columns.tolist() # Update valid list
        
        if nav_data.dropna().empty:
             console.print("[bold red]Critical Error:[/bold red] Still no overlapping data after cleaning. Cannot optimize.")
             raise typer.Exit(code=1)
        else:
             console.print(f"[green]Optimization preserved with {len(valid_funds)} funds. Common period: {len(nav_data.dropna())} days.[/green]")

    # Save Cleaned NAV Data for Inspection
    nav_export_path = "mf_balancer/data/nav_history.csv"
    os.makedirs(os.path.dirname(nav_export_path), exist_ok=True)
    nav_data.to_csv(nav_export_path)
    console.print(f"[dim]Saved historical NAV data to {nav_export_path}[/dim]")

    equity_holdings_optimized = {k: v for k, v in equity_holdings.items() if k in valid_funds}
    skipped_funds = set(equity_holdings.keys()) - set(valid_funds)
    
    if skipped_funds:
        console.print(f"\n[yellow]Warning:[/yellow] The following funds are excluded from optimization due to missing data: {skipped_funds}")

    # --- 6. Optimization Strategy Selection ---
    console.print("\n[bold cyan]Select Optimization Strategy:[/bold cyan]")
    console.print("1. [bold]Maximum Sharpe Ratio[/bold] (Standard, Unconstrained)")
    console.print("   [dim]- Finds the mathematically optimal portfolio.[/dim]")
    console.print("   [dim]- May result in 0% allocation to many funds (Concentrated).[/dim]")
    
    console.print("2. [bold]Constrained Optimization[/bold] (Diversified)")
    console.print("   [dim]- Finds the best portfolio considering your limits.[/dim]")
    console.print("   [dim]- Forces diversification (e.g., 'Don't put more than 20% in any fund').[/dim]")

    strategy_choice = IntPrompt.ask("Enter Choice", choices=["1", "2"], default=1)
    
    current_weight_bounds = (0, 1) # Default: 0% to 100%
    
    if strategy_choice == 2:
        console.print("\n[bold]Configure Constraints:[/bold]")
        max_w = FloatPrompt.ask("Enter Maximum weight per fund (e.g., 0.20 for 20%)", default=1.0)
        min_w = FloatPrompt.ask("Enter Minimum weight per fund (e.g., 0.05 for 5%)", default=0.00)
        
        # Validation
        if min_w * len(valid_funds) > 1.0:
             console.print(f"[bold red]Error:[/bold red] Minimum weight of {min_w:.0%} for {len(valid_funds)} funds requires {min_w * len(valid_funds):.0%} allocation, which is > 100%.")
             raise typer.Exit(code=1)
             
        current_weight_bounds = (min_w, max_w)
        console.print(f"[green]Applying Constraints: Min {min_w:.0%} | Max {max_w:.0%}[/green]")

    # --- 7. Optimize ---
    with console.status("[bold blue]Optimizing Portfolio..."):
        optimizer = PortfolioOptimizer(nav_data)
        optimizer.calculate_metrics()
        
        try:
            optimal_weights = optimizer.optimize_sharpe_ratio(
                risk_free_rate=risk_factor,
                weight_bounds=current_weight_bounds
            )
        except Exception:
            console.print("[bold red]Optimization failed due to constraints.[/bold red]")
            console.print("Try relaxing the constraints (e.g., reduce Min Weight or increase Max Weight).")
            raise typer.Exit(code=1)
        
    console.print(f"\n[bold]Optimal Equity Allocation:[/bold]")
    for f, w in optimal_weights.items():
        console.print(f"- {f}: {w*100:.1f}%")

    # --- 7. Allocate ---
    # We distribute the debt capital ONLY to the optimized funds
    allocator = Allocator(equity_holdings_optimized, debt_capital, optimal_weights, months)
    transfers = allocator.calculate_transfers()
    summary = allocator.get_summary()

    # --- 8. Report ---
    reporter = Reporter()
    # pass all equity holdings or only optimized? For now optimized logic.
    report_path = reporter.generate_report(summary, optimal_weights, transfers, duration=months)
    
    console.print(f"\n[bold green]Success![/bold green] Report saved to: [link={report_path}]{report_path}[/link]")

if __name__ == "__main__":
    app()
