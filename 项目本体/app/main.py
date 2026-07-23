from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import PROJECT_DIR, get_settings
from app.database import SessionLocal, get_session, initialize_database
from app.demo_data import seed_demo_data
from app.models import Draft, SourceItem, Topic


settings = get_settings()
templates = Jinja2Templates(directory=str(PROJECT_DIR / "app" / "templates"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    if settings.demo_mode:
        with SessionLocal() as session:
            seed_demo_data(session)
    yield


app = FastAPI(title="AI Radar", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "app" / "static")), name="static")


@app.get("/health")
def health_check() -> dict[str, str | bool]:
    return {"status": "ok", "environment": settings.app_env, "demo_mode": settings.demo_mode}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count = session.scalar(select(func.count(SourceItem.id)).where(SourceItem.fetched_at >= cutoff)) or 0
    topic_count = session.scalar(select(func.count(Topic.id))) or 0
    draft_count = session.scalar(select(func.count(Draft.id))) or 0
    topics = session.scalars(
        select(Topic).options(selectinload(Topic.evidences)).order_by(Topic.heat_score.desc())
    ).all()
    source_count = session.scalar(select(func.count(func.distinct(SourceItem.platform)))) or 0

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recent_count": recent_count,
            "topic_count": topic_count,
            "draft_count": draft_count,
            "source_count": source_count,
            "topics": topics,
            "demo_mode": settings.demo_mode,
        },
    )
