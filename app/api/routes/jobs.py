from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import ScrapeJob
from app.db.session import get_db
from app.schemas.listing import JobResponse, ListingsPageResponse, ListingResponse, ScrapeRequest
from app.services.job_service import JobService

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _job_to_response(job: ScrapeJob) -> JobResponse:
    return JobResponse(
        job_id=job.id,
        status=job.status,
        pincode=job.pincode,
        skill=job.skill,
        pages_scraped=job.pages_scraped,
        records_found=job.records_found,
        error_message=job.error_message,
        created_at=job.created_at.isoformat() if job.created_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
    )


@router.post("/scrape", response_model=JobResponse, status_code=202)
def start_scrape(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    service = JobService(db)
    job = service.create_job(request)
    background_tasks.add_task(service.run_job_sync, job.id, request.max_pages)
    return _job_to_response(job)


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    service = JobService(db)
    job = service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)
