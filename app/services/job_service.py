"""Job orchestration: scrape, persist, and export."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import JobStatus, Listing, ScrapeJob
from app.schemas.listing import ListingCreate, ScrapeRequest
from app.services.cleaner import clean_listing
from app.services.csv_export import export_listings
from app.services.exceptions import CaptchaError, PageLoadError
from app.services.scraper import ScraperService

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


class JobService:
    def __init__(self, db: Session, scraper: ScraperService | None = None):
        self.db = db
        self.scraper = scraper or ScraperService()

    def create_job(self, request: ScrapeRequest) -> ScrapeJob:
        job = ScrapeJob(
            pincode=request.pincode,
            skill=request.skill.strip(),
            status=JobStatus.PENDING.value,
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_job(self, job_id: str) -> ScrapeJob | None:
        return self.db.get(ScrapeJob, job_id)

    def start_job_async(self, job_id: str, max_pages: int | None = None) -> None:
        _executor.submit(self._run_job, job_id, max_pages)

    def run_job_sync(self, job_id: str, max_pages: int | None = None) -> ScrapeJob:
        self._execute_job(job_id, max_pages)
        job = self.get_job(job_id)
        assert job is not None
        return job

    def _run_job(self, job_id: str, max_pages: int | None) -> None:
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            service = JobService(db, self.scraper)
            service._execute_job(job_id, max_pages)
        finally:
            db.close()

    def _execute_job(self, job_id: str, max_pages: int | None) -> None:
        job = self.get_job(job_id)
        if job is None:
            return

        job.status = JobStatus.RUNNING.value
        self.db.commit()

        max_pages = max_pages or settings.max_pages
        inserted = 0

        try:
            result = self.scraper.run(
                pincode=job.pincode,
                skill=job.skill,
                max_pages=max_pages,
                job_id=job.id,
            )

            cleaned = [clean_listing(raw) for raw in result.listings]
            inserted = self._persist_listings(job, cleaned)

            job.pages_scraped = result.pages_scraped
            job.records_found = inserted

            if result.captcha_encountered:
                job.status = JobStatus.PARTIAL.value
                job.error_message = result.error_message
            elif result.error_message:
                job.status = JobStatus.PARTIAL.value if inserted else JobStatus.FAILED.value
                job.error_message = result.error_message
            else:
                job.status = JobStatus.COMPLETED.value

            if cleaned:
                export_listings(settings.output_dir, job.skill, job.pincode, cleaned)

            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.info(
                "job=%s finished status=%s records=%s",
                job.id,
                job.status,
                inserted,
            )

        except CaptchaError as exc:
            job.status = JobStatus.PARTIAL.value
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
        except PageLoadError as exc:
            job.status = JobStatus.PARTIAL.value if inserted else JobStatus.FAILED.value
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception as exc:
            logger.exception("job=%s failed", job_id)
            job.status = JobStatus.FAILED.value
            job.error_message = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            self.db.commit()

    def _persist_listings(self, job: ScrapeJob, listings: list[ListingCreate]) -> int:
        inserted = 0
        for item in listings:
            listing = Listing(
                job_id=job.id,
                pincode=job.pincode,
                skill=job.skill,
                name=item.name,
                phone=item.phone,
                email=item.email,
                address=item.address,
                rating=item.rating,
                reviews=item.reviews,
                category=item.category,
                source_url=item.source_url,
                raw_encoded_phone=item.raw_encoded_phone,
                dedup_key=item.dedup_key,
            )
            self.db.add(listing)
            try:
                self.db.commit()
                inserted += 1
            except IntegrityError:
                self.db.rollback()
        return inserted

    def list_listings(
        self,
        pincode: str,
        skill: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Listing], int]:
        filters = (Listing.pincode == pincode, Listing.skill == skill)
        total = self.db.scalar(
            select(func.count()).select_from(Listing).where(*filters)
        ) or 0
        items = self.db.scalars(
            select(Listing)
            .where(*filters)
            .order_by(Listing.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return list(items), total

    def get_all_listings_for_export(self, pincode: str, skill: str) -> list[ListingCreate]:
        rows = self.db.scalars(
            select(Listing).where(Listing.pincode == pincode, Listing.skill == skill)
        ).all()
        return [
            ListingCreate(
                name=row.name,
                phone=row.phone,
                email=row.email,
                address=row.address,
                rating=row.rating,
                reviews=row.reviews,
                category=row.category,
                source_url=row.source_url,
                raw_encoded_phone=row.raw_encoded_phone,
                dedup_key=row.dedup_key,
            )
            for row in rows
        ]
