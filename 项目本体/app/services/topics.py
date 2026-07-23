from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SourceItem, Topic, TopicEvidence


@dataclass(frozen=True)
class TopicRule:
    title: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class AggregationResult:
    topic_count: int
    evidence_count: int


TOPIC_RULES = (
    TopicRule("AI Agent 的可靠性与工作流", ("agent", "智能体", "tool use", "tool calling", "workflow", "reliability")),
    TopicRule("大模型推理与能力评测", ("llm", "reasoning", "large language model", "benchmark", "评测", "推理")),
    TopicRule("多模态模型与应用", ("multimodal", "vision-language", "多模态", "视觉语言")),
    TopicRule("AI 开源项目与开发者生态", ("open source", "github", "repository", "开源", "framework")),
    TopicRule("AI 研究与模型发布", ("model", "paper", "arxiv", "machine learning", "人工智能", "大模型")),
)


def _normalized_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def match_topic_rule(item: SourceItem) -> TopicRule:
    searchable = f"{item.title} {item.content}".casefold()
    scored_rules = [
        (sum(keyword in searchable for keyword in rule.keywords), rule)
        for rule in TOPIC_RULES
    ]
    score, rule = max(scored_rules, key=lambda entry: entry[0])
    if score:
        return rule
    return TOPIC_RULES[-1]


def calculate_heat_score(items: list[SourceItem]) -> float:
    if not items:
        return 0.0
    now = datetime.now(timezone.utc)
    latest = max(_normalized_time(item.published_at) for item in items)
    age_hours = max(0.0, (now - latest).total_seconds() / 3600)
    freshness_score = max(5.0, 35.0 - min(age_hours, 72.0) * 0.4)
    metric_total = 0.0
    for item in items:
        for value in item.metrics_json.values():
            if isinstance(value, (int, float)):
                metric_total += max(0.0, float(value))
    return round(min(100.0, 20.0 + len(items) * 11.0 + freshness_score + min(18.0, log1p(metric_total) * 2.5)), 1)


def summarize_items(items: list[SourceItem]) -> str:
    ordered_items = sorted(items, key=lambda item: _normalized_time(item.published_at), reverse=True)
    titles = "；".join(item.title for item in ordered_items[:2])
    return f"基于 {len(items)} 条可追溯来源聚合：{titles}。"


def aggregate_topics(session: Session) -> AggregationResult:
    items = session.scalars(select(SourceItem).order_by(SourceItem.published_at.desc())).all()
    grouped_items: dict[str, list[SourceItem]] = {}
    for item in items:
        grouped_items.setdefault(match_topic_rule(item).title, []).append(item)

    evidence_count = 0
    for title, grouped in grouped_items.items():
        latest_published_at = max(_normalized_time(item.published_at) for item in grouped)
        topic = session.scalar(select(Topic).where(Topic.title == title))
        if topic is None:
            topic = Topic(
                title=title,
                summary=summarize_items(grouped),
                heat_score=calculate_heat_score(grouped),
                freshness="近 24 小时" if (datetime.now(timezone.utc) - latest_published_at).total_seconds() < 86400 else "持续关注",
                latest_published_at=latest_published_at,
                status="active",
            )
            session.add(topic)
            session.flush()
        else:
            topic.summary = summarize_items(grouped)
            topic.heat_score = calculate_heat_score(grouped)
            topic.freshness = "近 24 小时" if (datetime.now(timezone.utc) - latest_published_at).total_seconds() < 86400 else "持续关注"
            topic.latest_published_at = latest_published_at
            topic.status = "active"

        existing_source_ids = set(
            session.scalars(select(TopicEvidence.source_item_id).where(TopicEvidence.topic_id == topic.id)).all()
        )
        for item in grouped:
            if item.id not in existing_source_ids:
                session.add(TopicEvidence(topic_id=topic.id, source_item_id=item.id, relevance_score=1.0))
                evidence_count += 1

    session.commit()
    return AggregationResult(topic_count=len(grouped_items), evidence_count=evidence_count)
