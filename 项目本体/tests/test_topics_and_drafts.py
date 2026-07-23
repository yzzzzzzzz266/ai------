from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from app.database import Base
from app.models import SourceItem, Topic, TopicEvidence
from app.services.drafts import EditorParameters, get_draft_generator
from app.services.topics import aggregate_topics


def source_item(title: str, content: str, url: str, published_at: datetime) -> SourceItem:
    return SourceItem(
        platform="测试来源",
        external_id=url.rsplit("/", 1)[-1],
        title=title,
        content=content,
        url=url,
        author="测试作者",
        published_at=published_at,
        fetched_at=published_at,
        metrics_json={"points": 10},
        language="en",
        raw_json={},
    )


def test_topic_aggregation_and_evidence_based_generation() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        session.add_all(
            [
                source_item("Open source AI agent workflow", "Agent reliability and tool calling details.", "https://example.com/agent", now),
                source_item("AI agent benchmark update", "A benchmark compares agent reasoning workflows.", "https://example.com/benchmark", now - timedelta(hours=2)),
                source_item("Multimodal reasoning model", "A multimodal benchmark paper for vision-language models.", "https://example.com/multimodal", now - timedelta(hours=4)),
            ]
        )
        session.commit()

        first_result = aggregate_topics(session)
        second_result = aggregate_topics(session)
        topic = session.scalar(
            select(Topic)
            .where(Topic.title == "AI Agent 的可靠性与工作流")
            .options(selectinload(Topic.evidences).selectinload(TopicEvidence.source_item))
        )

        parameters = EditorParameters(
            audience="开发者",
            writing_style="技术说明",
            stance="谨慎分析",
            target_length="800–1,200 字",
            banned_words="颠覆",
            required_facts="workflow",
            avoided_angles="不做性能排名",
        )
        generated = get_draft_generator().generate(topic, parameters, "技术拆解")

        assert first_result.topic_count == 2
        assert first_result.evidence_count == 3
        assert second_result.evidence_count == 0
        assert topic.heat_score > 0
        assert "https://example.com/agent" in generated.content_markdown
        assert "可追溯来源" in generated.content_markdown
        assert "现有信息不足以确认" not in generated.content_markdown
        assert generated.provider_name == "evidence-template"
