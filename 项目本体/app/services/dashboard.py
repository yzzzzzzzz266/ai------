from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import SourceItem
from app.services.collection import is_ai_related
from app.services.topics import TOPIC_RULES, _normalized_time, match_topic_rule


def _source_preview(item: SourceItem) -> dict[str, str]:
    return {
        "title": item.title,
        "url": item.url,
        "author": item.author or "来源未提供作者",
        "published_at": _normalized_time(item.published_at).strftime("%Y-%m-%d %H:%M UTC"),
        "summary": " ".join(item.content.split())[:220] or "来源未提供可展示的摘要。",
    }


def build_category_distribution(
    items: list[SourceItem],
    lookback_days: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    reference_time = _normalized_time(now or datetime.now(timezone.utc))
    cutoff = reference_time - timedelta(days=lookback_days)
    recent_items = [
        item
        for item in items
        if _normalized_time(item.published_at) >= cutoff and is_ai_related(item)
    ]
    categories: dict[str, dict[str, Any]] = {
        rule.title: {
            "id": f"category-{index + 1}",
            "name": rule.title,
            "source_count": 0,
            "percentage": 0.0,
            "platforms": {},
        }
        for index, rule in enumerate(TOPIC_RULES)
    }

    for item in recent_items:
        category = categories[match_topic_rule(item).title]
        category["source_count"] += 1
        platform = category["platforms"].setdefault(
            item.platform,
            {"name": item.platform, "source_count": 0, "sources": []},
        )
        platform["source_count"] += 1
        platform["sources"].append(_source_preview(item))

    total_count = len(recent_items)
    result: list[dict[str, Any]] = []
    for category in categories.values():
        platforms = []
        for platform in category["platforms"].values():
            platform["sources"].sort(key=lambda source: source["published_at"], reverse=True)
            platforms.append(platform)
        platforms.sort(key=lambda platform: (-platform["source_count"], platform["name"]))
        result.append(
            {
                "id": category["id"],
                "name": category["name"],
                "source_count": category["source_count"],
                "percentage": round(category["source_count"] / total_count * 100, 1) if total_count else 0.0,
                "platforms": platforms,
            }
        )
    return result
