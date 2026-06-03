from app.db.models import JobStatus, ScrapeJob


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_db_creates_tables_and_session_works(db_session, scrape_job_factory):
    job = scrape_job_factory(pincode="110001", skill="Plumbing")
    assert job.id is not None
    assert job.pincode == "110001"
    assert job.skill == "Plumbing"

    fetched = db_session.get(ScrapeJob, job.id)
    assert fetched is not None
    assert fetched.skill == "Plumbing"


def test_scrape_job_model_defaults(db_session):
    job = ScrapeJob(pincode="768028", skill="AC Repair")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    assert job.status == JobStatus.PENDING.value
    assert job.pages_scraped == 0
    assert job.records_found == 0
    assert job.error_message is None
    assert job.finished_at is None
