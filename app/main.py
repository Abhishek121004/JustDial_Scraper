import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import jobs, listings
from app.db.session import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="JustDial Scraper",
        description="Scrape JustDial business listings with FastAPI and SQLite",
        version="1.0.0",
        lifespan=lifespan,
    )

    app_dir = Path(__file__).parent
    app.mount("/static", StaticFiles(directory=str(app_dir / "static")), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        html_path = app_dir / "templates" / "index.html"
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.include_router(jobs.router)
    app.include_router(listings.router)

    return app


app = create_app()

