from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import PROJECT_DIR, get_settings
from app.database import SessionLocal, get_session, initialize_database
from app.demo_data import seed_demo_data
from app.models import Draft, SourceItem, Topic, TopicEvidence


settings = get_settings()
templates = Jinja2Templates(directory=str(PROJECT_DIR / "app" / "templates"))
DEFAULT_KEYWORDS = "LLM, agent, reasoning, multimodal, open source, model release, AI, 人工智能, 大模型, 智能体, 多模态, 开源模型"


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


def topic_query(keyword: str | None = None):
    statement = select(Topic).options(
        selectinload(Topic.evidences).selectinload(TopicEvidence.source_item),
        selectinload(Topic.drafts),
    )
    keywords = [item.strip() for item in (keyword or "").replace("，", ",").split(",") if item.strip()]
    if keywords:
        statement = statement.where(
            or_(
                *[
                    or_(Topic.title.ilike(f"%{item}%"), Topic.summary.ilike(f"%{item}%"))
                    for item in keywords
                ]
            )
        )
    return statement.order_by(Topic.heat_score.desc())


def get_topic_or_404(session: Session, topic_id: int) -> Topic:
    topic = session.scalar(topic_query().where(Topic.id == topic_id))
    if topic is None:
        raise HTTPException(status_code=404, detail="未找到该热点话题")
    return topic


def get_draft_or_404(session: Session, draft_id: int) -> Draft:
    draft = session.scalar(select(Draft).options(selectinload(Draft.topic)).where(Draft.id == draft_id))
    if draft is None:
        raise HTTPException(status_code=404, detail="未找到该草稿")
    return draft


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_count = session.scalar(select(func.count(SourceItem.id)).where(SourceItem.fetched_at >= cutoff)) or 0
    topic_count = session.scalar(select(func.count(Topic.id))) or 0
    draft_count = session.scalar(select(func.count(Draft.id))) or 0
    topics = session.scalars(topic_query(DEFAULT_KEYWORDS)).all()
    platforms = session.scalars(select(SourceItem.platform).distinct().order_by(SourceItem.platform)).all()

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "recent_count": recent_count,
            "topic_count": topic_count,
            "draft_count": draft_count,
            "source_count": len(platforms),
            "platforms": platforms,
            "topics": topics,
            "demo_mode": settings.demo_mode,
            "default_keywords": DEFAULT_KEYWORDS,
        },
    )


@app.get("/topics/fragment", response_class=HTMLResponse)
def topic_list_fragment(
    request: Request,
    keyword: str = "",
    session: Session = Depends(get_session),
) -> HTMLResponse:
    topics = session.scalars(topic_query(keyword)).all()
    return templates.TemplateResponse(
        request,
        "partials/topic_list.html",
        {"topics": topics, "keyword": keyword},
    )


@app.get("/topics/{topic_id}", response_class=HTMLResponse)
def topic_detail(topic_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    topic = get_topic_or_404(session, topic_id)
    return templates.TemplateResponse(request, "topic_detail.html", {"topic": topic, "demo_mode": settings.demo_mode})


@app.post("/topics/{topic_id}/drafts")
def create_draft(topic_id: int, session: Session = Depends(get_session)) -> RedirectResponse:
    topic = get_topic_or_404(session, topic_id)
    now = datetime.now(timezone.utc)
    draft = Draft(
        topic_id=topic.id,
        mode="新闻快讯",
        title=topic.title,
        content_markdown=f"# {topic.title}\n\n基于当前证据整理：\n",
        image_prompt=f"中文 AI 科技资讯插画，主题：{topic.title}，简洁专业，无文字，横向构图",
        editor_params_json={"audience": "普通读者", "tone": "新闻"},
        created_at=now,
        updated_at=now,
    )
    session.add(draft)
    session.commit()
    return RedirectResponse(url=f"/drafts/{draft.id}/edit", status_code=303)


@app.get("/drafts/{draft_id}/edit", response_class=HTMLResponse)
def edit_draft(draft_id: int, request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    draft = get_draft_or_404(session, draft_id)
    return templates.TemplateResponse(request, "draft_edit.html", {"draft": draft})


@app.post("/drafts/{draft_id}", response_class=HTMLResponse)
def save_draft(
    draft_id: int,
    request: Request,
    title: str = Form(),
    content_markdown: str = Form(),
    mode: str = Form(),
    image_prompt: str = Form(),
    session: Session = Depends(get_session),
) -> Response:
    draft = get_draft_or_404(session, draft_id)
    if not title.strip() or not content_markdown.strip():
        return templates.TemplateResponse(
            request,
            "partials/save_status.html",
            {"success": False, "message": "标题和正文不能为空。"},
            status_code=422,
        )

    draft.title = title.strip()
    draft.content_markdown = content_markdown.strip()
    draft.mode = mode
    draft.image_prompt = image_prompt.strip()
    draft.updated_at = datetime.now(timezone.utc)
    session.commit()

    if request.headers.get("HX-Request") == "true":
        return templates.TemplateResponse(
            request,
            "partials/save_status.html",
            {"success": True, "message": "草稿已保存。"},
        )
    return RedirectResponse(url=f"/drafts/{draft.id}/edit", status_code=303)


@app.get("/drafts/{draft_id}/export")
def export_draft(draft_id: int, session: Session = Depends(get_session)) -> Response:
    draft = get_draft_or_404(session, draft_id)
    filename = quote(f"AI-Radar-草稿-{draft.id}.md")
    markdown = f"# {draft.title}\n\n{draft.content_markdown}\n"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
