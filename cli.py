#!/usr/bin/env python3
"""CLI tool for Apigee Edge to X migration"""
import typer
import asyncio
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from models.migration_models import MigrationJob, MigrationJobCreate
from migration.migration_engine import MigrationEngine
from utils.config_loader import ConfigLoader
from utils.mock_data import MockDataGenerator

app = typer.Typer(
    name="apigee-migrate",
    help="Apigee Edge to Apigee X migration tool",
    add_completion=False
)
console = Console()


@app.command()
def full_migrate(
    config: str = typer.Option(..., "--config", "-c", help="Path to config file (YAML/JSON)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Perform dry run without actual import"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file for migration results"),
):
    """Run complete migration from Edge to Apigee X"""
    console.print("[bold blue]Apigee Edge → Apigee X Migration Tool[/bold blue]\n")
    
    try:
        # Load configuration
        config_data = ConfigLoader.load_config(config)
        edge_config = ConfigLoader.load_edge_config(config_data)
        x_config = ConfigLoader.load_apigee_x_config(config_data)
        
        # Create migration job
        job = MigrationJob(
            name=f"Migration-{edge_config.name}-to-{x_config.organization}",
            edge_org=edge_config.name,
            edge_env=edge_config.environments[0] if edge_config.environments else "prod",
            apigee_x_org=x_config.organization,
            apigee_x_env=x_config.environments[0] if x_config.environments else "prod",
            dry_run=dry_run
        )
        
        # Run migration
        console.print(f"[yellow]Starting migration job: {job.name}[/yellow]")
        if dry_run:
            console.print("[yellow]DRY RUN MODE - No actual imports will be performed[/yellow]\n")
        
        engine = MigrationEngine(job, mock_mode=True)  # Use mock mode for demo
        result = asyncio.run(engine.run_full_migration())
        
        # Display results
        _display_results(result)
        
        # Save results if output specified
        if output:
            with open(output, 'w') as f:
                json.dump(result.model_dump(), f, indent=2, default=str)
            console.print(f"\n[green]Results saved to {output}[/green]")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def export_edge(
    config: str = typer.Option(..., "--config", "-c", help="Path to config file"),
    output: str = typer.Option("edge_export.json", "--output", "-o", help="Output file"),
):
    """Export resources from Apigee Edge"""
    console.print("[bold blue]Exporting from Apigee Edge...[/bold blue]\n")
    
    try:
        config_data = ConfigLoader.load_config(config)
        edge_config = ConfigLoader.load_edge_config(config_data)
        
        from clients.edge_client import EdgeClient
        from migration.edge_exporter import EdgeExporter
        from utils.logger import MigrationLogger
        
        client = EdgeClient(base_url=edge_config.base_url, org=edge_config.name, mock_mode=True)
        logger = MigrationLogger("export-job")
        exporter = EdgeExporter(client, logger)
        
        export_data = asyncio.run(exporter.export_all(edge_config.environments[0]))
        
        # Save export
        with open(output, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)
        
        console.print(f"[green]✓ Export completed. Saved to {output}[/green]")
        _print_export_summary(export_data)
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def transform(
    input: str = typer.Option(..., "--input", "-i", help="Input file from export"),
    output: str = typer.Option("transformed.json", "--output", "-o", help="Output file"),
):
    """Transform Edge resources to Apigee X format"""
    console.print("[bold blue]Transforming resources...[/bold blue]\n")
    
    try:
        with open(input, 'r') as f:
            edge_data = json.load(f)
        
        from migration.transformer import ResourceTransformer
        from utils.logger import MigrationLogger
        
        logger = MigrationLogger("transform-job")
        transformer = ResourceTransformer(logger)
        
        x_data = transformer.transform_all(edge_data)
        
        with open(output, 'w') as f:
            json.dump(x_data, f, indent=2, default=str)
        
        console.print(f"[green]✓ Transformation completed. Saved to {output}[/green]")
        console.print(f"\nTransformation stats: {transformer.transformation_stats}")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def import_x(
    config: str = typer.Option(..., "--config", "-c", help="Path to config file"),
    input: str = typer.Option(..., "--input", "-i", help="Transformed data file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Dry run mode"),
):
    """Import transformed resources to Apigee X"""
    console.print("[bold blue]Importing to Apigee X...[/bold blue]\n")
    
    try:
        config_data = ConfigLoader.load_config(config)
        x_config = ConfigLoader.load_apigee_x_config(config_data)
        
        with open(input, 'r') as f:
            x_data = json.load(f)
        
        from clients.apigee_x_client import ApigeeXClient
        from migration.x_importer import ApigeeXImporter
        from utils.logger import MigrationLogger
        
        client = ApigeeXClient(
            project_id=x_config.project_id,
            organization=x_config.organization,
            mock_mode=True
        )
        logger = MigrationLogger("import-job")
        importer = ApigeeXImporter(client, logger, dry_run=dry_run)
        
        results = asyncio.run(importer.import_all(x_data, x_config.environments[0]))
        
        console.print(f"[green]✓ Import completed[/green]")
        console.print(f"\nImport stats: {importer.get_import_stats()}")
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def validate(
    edge_export: str = typer.Option(..., "--edge", help="Edge export file"),
    x_export: str = typer.Option(..., "--x", help="Apigee X export file"),
):
    """Validate migration by comparing Edge and X resources"""
    console.print("[bold blue]Validating migration...[/bold blue]\n")
    
    try:
        with open(edge_export, 'r') as f:
            edge_data = json.load(f)
        
        with open(x_export, 'r') as f:
            x_data = json.load(f)
        
        from clients.edge_client import EdgeClient
        from clients.apigee_x_client import ApigeeXClient
        from migration.validator import MigrationValidator
        from utils.logger import MigrationLogger
        
        edge_client = EdgeClient(base_url="", org="", mock_mode=True)
        x_client = ApigeeXClient(project_id="", organization="", mock_mode=True)
        logger = MigrationLogger("validate-job")
        
        validator = MigrationValidator(edge_client, x_client, logger)
        report = asyncio.run(validator.validate_migration(edge_data, x_data, "prod", "validate-job"))
        
        console.print(f"[green]✓ Validation completed[/green]\n")
        console.print(f"Status: [bold]{report.status.upper()}[/bold]")
        console.print(report.summary)
        
    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def generate_config(
    output: str = typer.Option("migration_config.yaml", "--output", "-o", help="Output config file"),
):
    """Generate a template configuration file"""
    config = ConfigLoader.create_default_config()
    ConfigLoader.save_config(config, output)
    console.print(f"[green]✓ Configuration template saved to {output}[/green]")
    console.print("\n[yellow]Please edit the file and add your credentials before running migration.[/yellow]")


@app.command()
def generate_mock_data(
    output: str = typer.Option("mock_export.json", "--output", "-o", help="Output file"),
):
    """Generate mock Edge export data for testing"""
    generator = MockDataGenerator()
    mock_data = generator.generate_complete_export()
    
    with open(output, 'w') as f:
        json.dump(mock_data, f, indent=2)
    
    console.print(f"[green]✓ Mock data generated: {output}[/green]")
    _print_export_summary(mock_data)


def _display_results(job: MigrationJob):
    """Display migration results"""
    table = Table(title="Migration Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Job Name", job.name)
    table.add_row("Status", job.status.value.upper())
    table.add_row("Total Resources", str(job.total_resources))
    table.add_row("Completed", str(job.completed_resources))
    table.add_row("Failed", str(job.failed_resources))
    table.add_row("Duration", str(job.completed_at - job.started_at) if job.completed_at else "N/A")
    
    console.print(table)


def _print_export_summary(export_data: dict):
    """Print export summary"""
    table = Table(title="Export Summary")
    table.add_column("Resource Type", style="cyan")
    table.add_column("Count", style="green")
    
    for resource_type, items in export_data.items():
        if isinstance(items, list):
            table.add_row(resource_type.replace('_', ' ').title(), str(len(items)))
    
    console.print(table)


if __name__ == "__main__":
    app()
