import json
import yaml
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from models import (
    FunctionConfig, CloudProvider, Runtime, TrafficPattern, ComparisonResult
)
from simulator import simulate_all_providers, ColdStartCostSimulator
from providers import get_provider_config


console = Console()


def load_config(filepath: str) -> FunctionConfig:
    with open(filepath, 'r') as f:
        if filepath.endswith('.yaml') or filepath.endswith('.yml'):
            data = yaml.safe_load(f)
        else:
            data = json.load(f)
    
    data['provider'] = CloudProvider(data['provider'])
    data['runtime'] = Runtime(data['runtime'])
    data['traffic_pattern'] = TrafficPattern(data['traffic_pattern'])
    
    return FunctionConfig(**data)


def create_sample_config() -> FunctionConfig:
    return FunctionConfig(
        provider=CloudProvider.AWS,
        runtime=Runtime.PYTHON,
        memory_mb=512,
        avg_duration_ms=200,
        monthly_invocations=1_000_000,
        traffic_pattern=TrafficPattern.BURSTY,
        has_heavy_dependencies=True,
        uses_vpc=False,
        provisioned_concurrency=0,
        min_instances=0,
    )


def format_currency(value: float) -> str:
    if value >= 1:
        return f"${value:.2f}"
    elif value >= 0.01:
        return f"${value:.4f}"
    else:
        return f"${value:.6f}"


def format_percent(value: float) -> str:
    return f"{value*100:.1f}%"


def print_simulation_result(result, show_optimal: bool = True):
    provider_name = result.provider.value.upper()
    
    table = Table(title=f"[bold cyan]{provider_name} Lambda Simulation[/bold cyan]", box=box.ROUNDED)
    table.add_column("Metric", style="white")
    table.add_column("Value", style="green", justify="right")
    
    table.add_row("Runtime", result.runtime.value)
    table.add_row("Memory", f"{result.memory_mb} MB")
    table.add_row("Traffic Pattern", result.traffic_pattern.value.capitalize())
    table.add_row("Cold Start Probability", format_percent(result.cold_start_probability))
    table.add_row("Avg Cold Start Latency", f"{result.avg_cold_start_ms:.0f} ms")
    table.add_row("Warm Duration", f"{result.warm_duration_ms:.0f} ms")
    table.add_row("Effective Duration", f"{result.effective_duration_ms:.0f} ms")
    table.add_row("", "")
    table.add_row("Monthly Request Cost", format_currency(result.monthly_requests_cost))
    table.add_row("Monthly Compute Cost", format_currency(result.monthly_compute_cost))
    table.add_row("[bold]Monthly Total Cost[/bold]", f"[bold]{format_currency(result.monthly_total_cost)}[/bold]")
    table.add_row("Free Tier Savings", format_currency(result.monthly_free_tier_savings))
    table.add_row("Cold Start Overhead", format_currency(result.cold_start_cost_overhead))
    table.add_row("Cost per Invocation", format_currency(result.cost_per_invocation))
    
    if show_optimal and result.optimal_memory_mb:
        table.add_row("", "")
        table.add_row("[bold]Optimal Memory[/bold]", f"[bold]{result.optimal_memory_mb} MB[/bold]")
        table.add_row("[bold]Optimal Cost[/bold]", f"[bold]{format_currency(result.optimal_cost)}[/bold]")
        table.add_row("[bold]Savings from Optimization[/bold]", f"[bold]{result.savings_from_optimization:.1f}%[/bold]")
    
    console.print(table)
    console.print()


def print_comparison(comparison: ComparisonResult):
    console.print(Panel.fit(
        f"Best: {comparison.best_provider.value.upper()} ({format_currency(comparison.best_cost)}/month)\n"
        f"Worst: {comparison.worst_provider.value.upper()} ({format_currency(comparison.worst_cost)}/month)\n\n"
        f"{comparison.recommendation}",
        title="Provider Comparison",
        border_style="green"
    ))
    
    table = Table(title="Cost Summary", box=box.ROUNDED)
    table.add_column("Provider", style="cyan")
    table.add_column("Memory", justify="right")
    table.add_column("Cold Start %", justify="right")
    table.add_column("Monthly Cost", justify="right")
    table.add_column("Cost/Inv", justify="right")
    table.add_column("Optimal Mem", justify="right")
    table.add_column("Savings", justify="right")
    
    for r in comparison.results:
        is_best = r.provider == comparison.best_provider
        if is_best:
            provider_str = f"[bold green]{r.provider.value.upper()}[/bold green]"
            mem_str = f"[bold green]{r.memory_mb} MB[/bold green]"
            cs_str = f"[bold green]{format_percent(r.cold_start_probability)}[/bold green]"
            cost_str = f"[bold green]{format_currency(r.monthly_total_cost)}[/bold green]"
            inv_str = f"[bold green]{format_currency(r.cost_per_invocation)}[/bold green]"
            opt_str = f"[bold green]{r.optimal_memory_mb or 'N/A'} MB[/bold green]"
            sav_str = f"[bold green]{r.savings_from_optimization or 0:.1f}%[/bold green]"
        else:
            provider_str = r.provider.value.upper()
            mem_str = f"{r.memory_mb} MB"
            cs_str = format_percent(r.cold_start_probability)
            cost_str = format_currency(r.monthly_total_cost)
            inv_str = format_currency(r.cost_per_invocation)
            opt_str = f"{r.optimal_memory_mb or 'N/A'} MB"
            sav_str = f"{r.savings_from_optimization or 0:.1f}%"
        
        table.add_row(provider_str, mem_str, cs_str, cost_str, inv_str, opt_str, sav_str)
    
    console.print(table)


@click.group()
def cli():
    """ColdStart Simulator - Serverless Cold-Start Cost Simulator
    
    Simulates cold-start frequency and cost across AWS Lambda, GCP Cloud Functions,
    and Azure Functions. Recommends optimal memory configuration for cost savings.
    """
    pass


@cli.command()
@click.option('--config', '-c', type=click.Path(exists=True), help='Config file (JSON or YAML)')
@click.option('--provider', '-p', type=click.Choice(['aws', 'gcp', 'azure']), default='aws')
@click.option('--runtime', '-r', type=click.Choice(['python3.11', 'nodejs20.x', 'java17', 'go1.21', 'dotnet8']), default='python3.11')
@click.option('--memory', '-m', type=int, default=512)
@click.option('--duration', '-d', type=int, default=200, help='Average warm duration in ms')
@click.option('--invocations', '-i', type=int, default=1_000_000, help='Monthly invocations')
@click.option('--pattern', type=click.Choice(['steady', 'bursty', 'spiky']), default='bursty')
@click.option('--heavy-deps/--light-deps', default=True)
@click.option('--vpc/--no-vpc', default=False)
@click.option('--provisioned', type=int, default=0, help='Provisioned concurrency (AWS only)')
@click.option('--min-instances', type=int, default=0, help='Min instances (Azure/GCP only)')
@click.option('--output', '-o', type=click.Choice(['table', 'json']), default='table')
def simulate(config, provider, runtime, memory, duration, invocations, pattern, heavy_deps, vpc, provisioned, min_instances, output):
    """Run cold-start cost simulation for a single provider or all providers."""
    
    if config:
        fn_config = load_config(config)
    else:
        fn_config = FunctionConfig(
            provider=CloudProvider(provider),
            runtime=Runtime(runtime),
            memory_mb=memory,
            avg_duration_ms=duration,
            monthly_invocations=invocations,
            traffic_pattern=TrafficPattern(pattern),
            has_heavy_dependencies=heavy_deps,
            uses_vpc=vpc,
            provisioned_concurrency=provisioned,
            min_instances=min_instances,
        )
    
    if fn_config.provider == CloudProvider.AWS:
        results = simulate_all_providers(fn_config)
    else:
        simulator = ColdStartCostSimulator(fn_config)
        results = [simulator.run_full_analysis()]
    
    if output == 'json':
        console.print(json.dumps([r.model_dump() for r in results], indent=2))
    else:
        for r in results:
            print_simulation_result(r)
    
    if len(results) > 1:
        best = min(results, key=lambda r: r.monthly_total_cost)
        worst = max(results, key=lambda r: r.monthly_total_cost)
        
        recommendation = _generate_recommendation(results, fn_config)
        
        comparison = ComparisonResult(
            function_config=fn_config,
            results=results,
            best_provider=best.provider,
            best_cost=best.monthly_total_cost,
            worst_provider=worst.provider,
            worst_cost=worst.monthly_total_cost,
            recommendation=recommendation,
        )
        print_comparison(comparison)


@cli.command()
@click.option('--output', '-o', type=click.Path(), default='sample_config.yaml')
def generate_sample(output):
    """Generate a sample configuration file."""
    config = create_sample_config()
    
    data = {
        'provider': config.provider.value,
        'runtime': config.runtime.value,
        'memory_mb': config.memory_mb,
        'avg_duration_ms': config.avg_duration_ms,
        'monthly_invocations': config.monthly_invocations,
        'traffic_pattern': config.traffic_pattern.value,
        'has_heavy_dependencies': config.has_heavy_dependencies,
        'uses_vpc': config.uses_vpc,
        'provisioned_concurrency': config.provisioned_concurrency,
        'min_instances': config.min_instances,
    }
    
    with open(output, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    console.print(f"[green]Sample config written to {output}[/green]")
    console.print("\nRun with: [cyan]coldstart simulate -c sample_config.yaml[/cyan]")


@cli.command()
def providers():
    """List supported providers and their configurations."""
    table = Table(title="Supported Cloud Providers", box=box.ROUNDED)
    table.add_column("Provider", style="cyan")
    table.add_column("Request Price/M", justify="right")
    table.add_column("Compute Price/GB-s", justify="right")
    table.add_column("Free Tier Req/M", justify="right")
    table.add_column("Free Tier GB-s/M", justify="right")
    table.add_column("Memory Options", justify="left")
    table.add_column("Max Timeout", justify="right")
    
    for provider in CloudProvider:
        pc = get_provider_config(provider)
        mem_str = ", ".join(f"{m}MB" for m in pc.memory_options[:5]) + ("..." if len(pc.memory_options) > 5 else "")
        table.add_row(
            provider.value.upper(),
            f"${pc.pricing.request_price_per_million:.2f}",
            f"${pc.pricing.compute_price_per_gb_second:.8f}",
            f"{pc.pricing.free_tier_requests_per_month:,}",
            f"{pc.pricing.free_tier_gb_seconds_per_month:,}",
            mem_str,
            f"{pc.max_timeout_seconds}s"
        )
    
    console.print(table)


def _generate_recommendation(results: list, config: FunctionConfig) -> str:
    best = min(results, key=lambda r: r.monthly_total_cost)
    worst = max(results, key=lambda r: r.monthly_total_cost)
    
    if worst.monthly_total_cost == 0:
        savings = 0.0
    else:
        savings = ((worst.monthly_total_cost - best.monthly_total_cost) / worst.monthly_total_cost) * 100
    
    if config.traffic_pattern == TrafficPattern.SPIKY:
        return (f"For spiky traffic, {best.provider.value.upper()} wins by {savings:.0f}% due to "
                f"better cold-start handling. Consider min instances on GCP/Azure.")
    elif config.traffic_pattern == TrafficPattern.BURSTY:
        return (f"For bursty traffic, {best.provider.value.upper()} is {savings:.0f}% cheaper. "
                f"Provisioned concurrency on AWS can help if cold starts >300ms.")
    else:
        return (f"For steady traffic, {best.provider.value.upper()} is optimal. "
                f"Memory tuning saves up to {max(r.savings_from_optimization or 0 for r in results):.0f}%.")


if __name__ == '__main__':
    cli()