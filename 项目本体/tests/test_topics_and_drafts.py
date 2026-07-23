from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.database import Base
from app.models import SourceItem, Topic, TopicEvidence
from app.services.drafts import EditorParameters, get_draft_generator
from app.services.topics import aggregate_topics, calculate_heat_score, source_weight_for_item


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
        assert "公开采集 · 测试来源" in generated.content_markdown
        assert "可追溯来源" in generated.content_markdown
        assert "现有信息不足以确认" not in generated.content_markdown
        assert generated.provider_name == "evidence-template"


def test_source_and_authority_weights_change_heat_score() -> None:
    now = datetime.now(timezone.utc)
    settings = Settings(
        source_weight_arxiv=1.5,
        source_weight_hacker_news=0.5,
        source_weight_x=1.0,
        x_author_usernames="frontier_lab",
        authority_author_bonus=0.8,
    )
    arxiv_item = SourceItem(
        platform="arXiv", external_id="paper", title="AI reasoning paper", content="AI benchmark paper",
        url="https://example.com/paper", author="Researcher", published_at=now, fetched_at=now,
        metrics_json={"points": 10}, language="en", raw_json={},
    )
    hacker_news_item = SourceItem(
        platform="Hacker News", external_id="hn", title="AI reasoning paper", content="AI benchmark paper",
        url="https://example.com/hn", author="reader", published_at=now, fetched_at=now,
        metrics_json={"points": 10}, language="en", raw_json={},
    )
    trusted_x_item = SourceItem(
        platform="X", external_id="x", title="AI agent release", content="AI agent model release",
        url="https://example.com/x", author="@frontier_lab", published_at=now, fetched_at=now,
        metrics_json={}, language="en", raw_json={},
    )

    assert calculate_heat_score([arxiv_item], settings) > calculate_heat_score([hacker_news_item], settings)
    assert source_weight_for_item(trusted_x_item, settings) == 1.8


def test_reaggregation_refreshes_existing_evidence_weights() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        session.add(
            SourceItem(
                platform="arXiv",
                external_id="refresh-paper",
                title="AI reasoning paper",
                content="AI model benchmark paper",
                url="https://example.com/refresh-paper",
                author="Researcher",
                published_at=now,
                fetched_at=now,
                metrics_json={},
                language="en",
                raw_json={},
            )
        )
        session.commit()

        aggregate_topics(session, Settings(source_weight_arxiv=1.0))
        evidence = session.scalar(select(TopicEvidence))
        assert evidence.relevance_score == 1.0

        aggregate_topics(session, Settings(source_weight_arxiv=1.7))
        session.refresh(evidence)
        assert evidence.relevance_score == 1.7
