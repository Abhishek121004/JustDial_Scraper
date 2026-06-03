from pydantic import BaseModel, Field


class RawListing(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    rating: str = ""
    reviews: str = ""
    category: str = ""
    source_url: str = ""
    raw_encoded_phone: str | None = None
    needs_click_fallback: bool = False


class ListingCreate(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    rating: str = ""
    reviews: str = ""
    category: str = ""
    source_url: str = ""
    raw_encoded_phone: str | None = None
    dedup_key: str = ""


class ScrapeRequest(BaseModel):
    pincode: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    skill: str = Field(..., min_length=1, max_length=255)
    max_pages: int | None = Field(default=None, ge=1, le=100)


class JobResponse(BaseModel):
    job_id: str
    status: str
    pincode: str
    skill: str
    pages_scraped: int
    records_found: int
    error_message: str | None = None
    created_at: str | None = None
    finished_at: str | None = None


class ListingResponse(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    address: str
    rating: str
    reviews: str
    category: str
    source_url: str

    model_config = {"from_attributes": True}


class ListingsPageResponse(BaseModel):
    items: list[ListingResponse]
    total: int
    page: int
    page_size: int
