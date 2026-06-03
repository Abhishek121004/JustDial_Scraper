from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from app.cli import cli
from app.db.models import JobStatus, Listing
from app.schemas.listing import RawListing, ScrapeRequest
from app.services.job_service import JobService
from app.services.scraper import ScrapeResult


@pytest.fixture
def mock_scraper():
    scraper = MagicMock()
    scraper.run.return_value = ScrapeResult(
        listings=[
            RawListing(
                name="Test Business",
                phone="9876543210",
                source_url="https://www.justdial.com/768028/ac-repair",
            )
        ],
        pages_scraped=1,
    )
    return scraper


def test_post_scrape_returns_job_id(client, mock_scraper):
    with patch("app.api.routes.jobs.JobService") as mock_service_cls:
        mock_service = MagicMock()
        mock_job = MagicMock()
        mock_job.id = "job-123"
        mock_job.status = "pending"
        mock_job.pincode = "768028"
        mock_job.skill = "AC Repair"
        mock_job.pages_scraped = 0
        mock_job.records_found = 0
        mock_job.error_message = None
        mock_job.created_at = None
        mock_job.finished_at = None
        mock_service.create_job.return_value = mock_job
        mock_service_cls.return_value = mock_service

        response = client.post(
            "/api/v1/scrape",
            json={"pincode": "768028", "skill": "AC Repair", "max_pages": 3},
        )

    assert response.status_code == 202
    assert response.json()["job_id"] == "job-123"


def test_get_job_not_found(client):
    response = client.get("/api/v1/jobs/nonexistent")
    assert response.status_code == 404


def test_list_listings(client, db_session, mock_scraper):
    service = JobService(db_session, mock_scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    response = client.get("/api/v1/listings", params={"pincode": "768028", "skill": "AC Repair"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Test Business"


def test_export_csv(client, db_session, mock_scraper, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.output_dir", str(tmp_path))
    service = JobService(db_session, mock_scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    response = client.get(
        "/api/v1/export/csv",
        params={"pincode": "768028", "skill": "AC Repair"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")


def test_invalid_pincode_returns_422(client):
    response = client.post("/api/v1/scrape", json={"pincode": "abc", "skill": "AC Repair"})
    assert response.status_code == 422


def test_cli_scrape(db_session, mock_scraper, monkeypatch):
    monkeypatch.setattr("app.cli.SessionLocal", lambda: db_session)
    monkeypatch.setattr("app.cli.init_db", lambda: None)
    monkeypatch.setattr("app.cli.JobService", lambda db, scraper=None: JobService(db, mock_scraper))

    runner = CliRunner()
    result = runner.invoke(cli, ["scrape", "--pincode", "768028", "--skill", "AC Repair"])
    assert result.exit_code == 0
    assert "finished" in result.stdout.lower() or "Created job" in result.stdout


def test_cli_export(db_session, mock_scraper, tmp_path, monkeypatch):
    monkeypatch.setattr("app.cli.SessionLocal", lambda: db_session)
    monkeypatch.setattr("app.cli.init_db", lambda: None)
    monkeypatch.setattr("app.config.settings.output_dir", str(tmp_path))

    service = JobService(db_session, mock_scraper)
    job = service.create_job(ScrapeRequest(pincode="768028", skill="AC Repair"))
    service.run_job_sync(job.id)

    runner = CliRunner()
    result = runner.invoke(
        cli, ["export", "--pincode", "768028", "--skill", "AC Repair"]
    )
    assert result.exit_code == 0
    assert "records saved" in result.stdout
