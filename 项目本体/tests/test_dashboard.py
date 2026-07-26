from datetime import datetime, timedelta, timezone

from app.models import SourceItem
from app.services.dashboard import build_category_distribution


def source_item(title: str, content: str, platform: str, published_at: datetime) -> SourceItem:
    return SourceItem(
        platform=platform,
        external_id=title,
        title=title,
        content=content,
        url=f"https://example.com/{title.replace(' ', '-')}",
        author="Test author",
        published_at=published_at,
        fetched_at=published_at,
        metrics_json={},
        language="en",
        raw_json={},
    )


def test_category_distribution_uses_recent_sources_and_groups_platforms() -> None:
    now = datetime.now(timezone.utc)
    distribution = build_category_distribution(
        [
            source_item("Agent release", "AI agent tool calling workflow", "GitHub", now),
            source_item("Agent benchmark", "AI agent reliability", "arXiv", now - timedelta(days=1)),
            source_item("Vision model", "multimodal vision-language model", "RSS", now - timedelta(days=2)),
            source_item("Old model", "AI model paper", "RSS", now - timedelta(days=8)),
        ],
        lookback_days=7,
        now=now,
    )

    active_categories = [category for category in distribution if category["source_count"]]
    assert sum(category["source_count"] for category in active_categories) == 3
    assert sum(category["percentage"] for category in active_categories) == 100.0
    agent_category = next(category for category in active_categories if category["source_count"] == 2)
    assert {platform["name"] for platform in agent_category["platforms"]} == {"GitHub", "arXiv"}
