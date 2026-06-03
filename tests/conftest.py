import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import ScrapeJob
from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Session:
    session = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autocommit=False, autoflush=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def scrape_job_factory(db_session):
    def _factory(**kwargs):
        job = ScrapeJob(
            pincode=kwargs.get("pincode", "768028"),
            skill=kwargs.get("skill", "AC Repair"),
            status=kwargs.get("status", "pending"),
            pages_scraped=kwargs.get("pages_scraped", 0),
            records_found=kwargs.get("records_found", 0),
            error_message=kwargs.get("error_message"),
        )
        db_session.add(job)
        db_session.commit()
        db_session.refresh(job)
        return job

    return _factory
