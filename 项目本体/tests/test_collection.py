from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import Base
from app.models import CollectionRun, SourceItem
from app.services import collection
from app.services.collection import SourceItemPayload, collect_sources, persist_items


def make_payload(title: str, url: str, external_id: str | None = None) -> SourceItemPayload:
    return SourceItemPayload(
        platform="测试来源",
        external_id=external_id,
        title=title,
        content="AI agent 的公开测试摘要",
        url=url,
        author="测试作者",
        published_at=datetime.now(timezone.utc),
        metrics_json={},
        language="zh",
        raw_json={},
    )


def test_persist_items_filters_and_deduplicates_url_hash() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        source = make_payload("AI Agent 可靠性测试", "https://example.com/agent")
        irrelevant = make_payload("普通体育新闻", "https://example.com/sports")
        irrelevant = SourceItemPayload(**{**irrelevant.__dict__, "content": "无关摘要"})

        first_stats = persist_items(session, [source, irrelevant])
        second_stats = persist_items(session, [source])

        assert first_stats.added_count == 1
        assert first_stats.filtered_count == 1
        assert second_stats.duplicate_count == 1
        assert session.scalar(select(func.count(SourceItem.id))) == 1


def test_collection_continues_after_source_failure(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    class WorkingAdapter:
        name = "可用来源"

        def fetch(self, _client):
            return [make_payload("Open AI agent workflow", "https://example.com/workflow", "working-1")]

    class FailingAdapter:
        name = "失败来源"

        def fetch(self, _client):
            raise RuntimeError("模拟网络超时")

    monkeypatch.setattr(collection, "build_adapters", lambda _settings: [WorkingAdapter(), FailingAdapter()])
    collect_sources(factory, Settings())
    collect_sources(factory, Settings())

    with factory() as session:
        successful_runs = session.scalars(
            select(CollectionRun).where(CollectionRun.source_name == "可用来源").order_by(CollectionRun.id)
        ).all()
        failed_runs = session.scalars(select(CollectionRun).where(CollectionRun.source_name == "失败来源")).all()

        assert successful_runs[0].status == "success"
        assert successful_runs[0].added_count == 1
        assert successful_runs[1].duplicate_count == 1
        assert failed_runs[0].status == "failed"
        assert "模拟网络超时" in failed_runs[0].error_message
