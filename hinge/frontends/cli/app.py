"""Typer-based CLI entry point.

Usage:

    hinge ingest path/to/events.jsonl --reader numfocus
    hinge export --dataset <id> --projection dev-interaction --format gml -o out.gml
    hinge list datasets
    hinge list projections
    hinge list readers
    hinge list exporters
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hinge.config.logging_setup import setup_logging
from hinge.frontends import lib

setup_logging()

app = typer.Typer(help="hinge — Heterogeneous Information Network tool", no_args_is_help=True)
list_app = typer.Typer(help="List available resources", no_args_is_help=True)
app.add_typer(list_app, name="list")

console = Console()


@app.command()
def ingest(
    path: Path = typer.Argument(..., exists=True, readable=True, help="Dataset file."),
    reader: str = typer.Option(..., "--reader", "-r", help="Reader name (e.g. numfocus)."),
    fast_hin: bool = typer.Option(
        False,
        "--fast-hin",
        help="Use DuckDB JSONL -> HIN contract-table ingest for NumFocus Actions files.",
    ),
) -> None:
    """Read a dataset file, extract typed nodes/edges, persist to the DuckDB store."""
    report = lib.ingest(path, reader=reader, fast_hin=fast_hin)
    console.print(
        f"[green]ingested[/green] {report.elements_read:,} elements "
        f"→ {report.nodes_upserted:,} nodes, {report.edges_upserted:,} edges "
        f"({report.violation_count} violations)\n"
        f"[bold]Dataset ID:[/bold] {report.dataset_id}"
    )


@app.command()
def export(
    dataset: str = typer.Option(..., "--dataset", "-d", help="Dataset ID from a previous ingest."),
    projection: str = typer.Option(..., "--projection", "-p", help="Projection name."),
    format_: str = typer.Option(..., "--format", "-f", help="Exporter name (e.g. gml)."),
    output: Path = typer.Option(..., "--output", "-o", help="Output file."),
) -> None:
    """Run a projection over a specific dataset and export the result."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as sink:
        receipt = lib.export(projection_name=projection, dataset_id=dataset, fmt=format_, sink=sink)
    console.print(
        f"[green]exported[/green] {receipt.node_count:,} nodes, "
        f"{receipt.edge_count:,} edges → {output} "
        f"(snapshot {receipt.snapshot_id[:12] if receipt.snapshot_id else '—'})"
    )


@app.command("export-sql")
def export_sql(
    sql: Path = typer.Argument(..., exists=True, readable=True, help="Custom dbt model SQL file."),
    dataset: str = typer.Option(..., "--dataset", "-d", help="Dataset ID from a previous ingest."),
    format_: str = typer.Option(..., "--format", "-f", help="Exporter name (e.g. gml)."),
    output: Path = typer.Option(..., "--output", "-o", help="Output file."),
    name: str | None = typer.Option(None, "--name", help="dbt model name; defaults to SQL stem."),
) -> None:
    """Run a local SQL projection that can use the built-in dbt HIN macros."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as sink:
        receipt = lib.export_sql_projection(
            sql_path=sql, dataset_id=dataset, fmt=format_, sink=sink, name=name
        )
    console.print(
        f"[green]exported[/green] {receipt.node_count:,} nodes, "
        f"{receipt.edge_count:,} edges → {output} "
        f"(snapshot {receipt.snapshot_id[:12] if receipt.snapshot_id else '—'})"
    )


@list_app.command("datasets")
def list_datasets() -> None:
    """Show all ingested datasets stored in the DuckDB file."""
    datasets = lib.list_datasets()
    if not datasets:
        console.print("[yellow]No datasets ingested yet.[/yellow]")
        return
    table = Table("dataset_id", "reader", "path", "ingested_at", "nodes", "edges")
    for d in datasets:
        table.add_row(
            d.dataset_id,
            d.reader,
            d.path,
            d.ingested_at.strftime("%Y-%m-%d %H:%M:%S"),
            str(d.node_count) if d.node_count is not None else "—",
            str(d.edge_count) if d.edge_count is not None else "—",
        )
    console.print(table)


@list_app.command("projections")
def list_projections() -> None:
    """List all registered projection names (pass to --projection on export)."""
    table = Table("name")
    for name in lib.list_projections():
        table.add_row(name)
    console.print(table)


@list_app.command("exporters")
def list_exporters() -> None:
    """List all registered exporter names (pass to --format on export)."""
    table = Table("name")
    for name in lib.list_exporters():
        table.add_row(name)
    console.print(table)


@list_app.command("readers")
def list_readers() -> None:
    """List all registered reader names (pass to --reader on ingest)."""
    table = Table("name")
    for name in lib.list_readers():
        table.add_row(name)
    console.print(table)


if __name__ == "__main__":
    app()
