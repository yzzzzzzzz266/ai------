from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import log1p

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
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


def _configured_values(value: str) -> set[str]:
    return {entry.strip().casefold().lstrip("@") for entry in value.replace("\n", ",").split(",") if entry.strip()}


def platform_weight(platform: str, settings: Settings) -> float:
    weights = {
        "arxiv": settings.source_weight_arxiv,
        "github": settings.source_weight_github,
        "hacker news": settings.source_weight_hacker_news,
        "rss": settings.source_weight_rss,
        "x": settings.source_weight_x,
        "bilibili": settings.source_weight_bilibili,
    }
    return weights.get(platform.casefold(), settings.source_weight_default)


def is_authoritative_source(item: SourceItem, settings: Settings) -> bool:
    author = (item.author or "").strip().casefold().lstrip("@")
    if author and author in _configured_values(settings.trusted_author_names):
        return True
    if item.platform.casefold() == "x" and author in _configured_values(settings.x_author_usernames):
        return True
    if item.platform.casefold() == "bilibili":
        author_mid = str(item.raw_json.get("mid", "")).strip().casefold()
        return author_mid in _configured_values(settings.bilibili_author_mids)
    return False


def source_weight_for_item(item: SourceItem, settings: Settings) -> float:
    weight = platform_weight(item.platform, settings)
    if is_authoritative_source(item, settings):
        weight *= 1 + settings.authority_author_bonus
    return round(weight, 3)


def build_topic_profile(items: list[SourceItem], settings: Settings) -> dict[str, float | int | str]:
    platform_counts: dict[str, int] = {}
    weights = []
    authoritative_count = 0
    for item in items:
        platform_counts[item.platform] = platform_counts.get(item.platform, 0) + 1
        weights.append(source_weight_for_item(item, settings))
        authoritative_count += int(is_authoritative_source(item, settings))
    platform_summary = " · ".join(
        f"{platform} {count}" for platform, count in sorted(platform_counts.items(), key=lambda entry: (-entry[1], entry[0]))
    )
    return {
        "authoritative_count": authoritative_count,
        "weighted_source_count": round(sum(weights), 2),
        "average_source_weight": round(sum(weights) / len(weights), 2) if weights else 0.0,
        "platform_summary": platform_summary,
    }


def calculate_heat_score(items: list[SourceItem], settings: Settings | None = None) -> float:
    if not items:
        return 0.0
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    latest = max(_normalized_time(item.published_at) for item in items)
    age_hours = max(0.0, (now - latest).total_seconds() / 3600)
    freshness_score = max(5.0, 35.0 - min(age_hours, 72.0) * 0.4) * settings.heat_freshness_weight
    metric_total = 0.0
    for item in items:
        item_weight = source_weight_for_item(item, settings)
        for value in item.metrics_json.values():
            if isinstance(value, (int, float)):
                metric_total += max(0.0, float(value)) * item_weight
    weighted_source_count = sum(source_weight_for_item(item, settings) for item in items)
    engagement_score = min(18.0, log1p(metric_total) * 2.5) * settings.heat_engagement_weight
    return round(min(100.0, 20.0 + weighted_source_count * 11.0 + freshness_score + engagement_score), 1)


def summarize_items(items: list[SourceItem]) -> str:
    ordered_items = sorted(items, key=lambda item: _normalized_time(item.published_at), reverse=True)
    titles = "；".join(item.title for item in ordered_items[:2])
    return f"基于 {len(items)} 条可追溯来源聚合：{titles}。"


def aggregate_topics(session: Session, settings: Settings | None = None) -> AggregationResult:
    settings = settings or get_settings()
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
                heat_score=calculate_heat_score(grouped, settings),
                freshness="近 24 小时" if (datetime.now(timezone.utc) - latest_published_at).total_seconds() < 86400 else "持续关注",
                latest_published_at=latest_published_at,
                status="active",
            )
            session.add(topic)
            session.flush()
        else:
            topic.summary = summarize_items(grouped)
            topic.heat_score = calculate_heat_score(grouped, settings)
            topic.freshness = "近 24 小时" if (datetime.now(timezone.utc) - latest_published_at).total_seconds() < 86400 else "持续关注"
            topic.latest_published_at = latest_published_at
            topic.status = "active"

        existing_evidence = {
            evidence.source_item_id: evidence
            for evidence in session.scalars(select(TopicEvidence).where(TopicEvidence.topic_id == topic.id)).all()
        }
        for item in grouped:
            relevance_score = source_weight_for_item(item, settings)
            evidence = existing_evidence.get(item.id)
            if evidence is None:
                session.add(TopicEvidence(topic_id=topic.id, source_item_id=item.id, relevance_score=relevance_score))
                evidence_count += 1
            else:
                evidence.relevance_score = relevance_score

    session.commit()
    return AggregationResult(topic_count=len(grouped_items), evidence_count=evidence_count)
