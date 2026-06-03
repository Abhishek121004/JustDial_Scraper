from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.schemas.listing import ListingsPageResponse, ListingResponse
from app.services.csv_export import csv_path, export_listings
from app.services.job_service import JobService

router = APIRouter(prefix="/api/v1", tags=["listings"])


@router.get("/listings", response_model=ListingsPageResponse)
def list_listings(
    pincode: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    skill: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    service = JobService(db)
    items, total = service.list_listings(pincode, skill, page, page_size)
    return ListingsPageResponse(
        items=[ListingResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export/csv")
def export_csv(
    pincode: str = Query(..., min_length=6, max_length=6, pattern=r"^\d{6}$"),
    skill: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    service = JobService(db)
    listings = service.get_all_listings_for_export(pincode, skill)
    if not listings:
        raise HTTPException(status_code=404, detail="No listings found for this search")

    path, _ = export_listings(settings.output_dir, skill, pincode, listings)
    if not Path(path).exists():
        raise HTTPException(status_code=500, detail="Failed to generate CSV")

    return FileResponse(
        path=path,
        media_type="text/csv",
        filename=path.name,
    )
