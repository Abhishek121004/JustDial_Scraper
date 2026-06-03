"""Typer CLI for JustDial scraper."""

import typer
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal, init_db
from app.schemas.listing import ScrapeRequest
from app.services.csv_export import export_listings
from app.services.job_service import JobService

cli = typer.Typer(help="JustDial Scraper CLI")


def _get_db() -> Session:
    init_db()
    return SessionLocal()


@cli.command("scrape")
def scrape(
    pincode: str = typer.Option(..., "--pincode", help="6-digit pincode"),
    skill: str = typer.Option(..., "--skill", help="Service/skill to search"),
    max_pages: int = typer.Option(settings.max_pages, "--max-pages", help="Max pages to scrape"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for job completion"),
):
    """Start a scrape job and optionally wait for completion."""
    db = _get_db()
    try:
        service = JobService(db)
        job = service.create_job(ScrapeRequest(pincode=pincode, skill=skill, max_pages=max_pages))
        typer.echo(f"Created job {job.id}")

        if wait:
            service.run_job_sync(job.id, max_pages)
            job = service.get_job(job.id)
            typer.echo(
                f"Job {job.id} finished: status={job.status}, records={job.records_found}"
            )
            if job.error_message:
                typer.echo(f"Note: {job.error_message}")
        else:
            service.start_job_async(job.id, max_pages)
            typer.echo("Job started in background")
    finally:
        db.close()


@cli.command("status")
def status(job_id: str = typer.Option(..., "--job-id", help="Scrape job ID")):
    """Check scrape job status."""
    db = _get_db()
    try:
        service = JobService(db)
        job = service.get_job(job_id)
        if job is None:
            typer.echo(f"Job {job_id} not found", err=True)
            raise typer.Exit(code=1)
        typer.echo(
            f"Job {job.id}: status={job.status}, pages={job.pages_scraped}, "
            f"records={job.records_found}"
        )
        if job.error_message:
            typer.echo(f"Error: {job.error_message}")
    finally:
        db.close()


@cli.command("export")
def export(
    pincode: str = typer.Option(..., "--pincode"),
    skill: str = typer.Option(..., "--skill"),
):
    """Export listings to CSV."""
    db = _get_db()
    try:
        service = JobService(db)
        listings = service.get_all_listings_for_export(pincode, skill)
        if not listings:
            typer.echo("No listings found", err=True)
            raise typer.Exit(code=1)
        path, count = export_listings(settings.output_dir, skill, pincode, listings)
        typer.echo(f"{count} records saved to {path}")
    finally:
        db.close()


def main():
    cli()


if __name__ == "__main__":
    main()
