from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings
from app.models import SourceItem
from app.services.creator import _chat
from app.services.collection import is_ai_related
from app.services.topics import TOPIC_RULES, _normalized_time, match_topic_rule


def _source_preview(item: SourceItem) -> dict[str, str]:
    localized = (item.raw_json or {}).get("dashboard_zh", {})
    return {
        "title": localized.get("title", item.title),
        "url": item.url,
        "author": item.author or "来源未提供作者",
        "published_at": _normalized_time(item.published_at).strftime("%Y-%m-%d %H:%M UTC"),
        "summary": localized.get("summary", " ".join(item.content.split())[:220] or "来源未提供可展示的摘要。"),
    }


def _parse_translations(value: str) -> dict[int, dict[str, str]]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
    try:
        records = json.loads(cleaned)
    except json.JSONDecodeError:
        return {}
    if not isinstance(records, list):
        return {}
    translations: dict[int, dict[str, str]] = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), int):
            continue
        title = record.get("title")
        summary = record.get("summary")
        if isinstance(title, str) and title.strip() and isinstance(summary, str) and summary.strip():
            translations[record["id"]] = {"title": title.strip(), "summary": summary.strip()}
    return translations


def localize_dashboard_previews(items: list[SourceItem], settings: Settings) -> bool:
    untranslated = [
        item
        for item in items
        if not (item.raw_json or {}).get("dashboard_zh")
        and (
            not re.search(r"[\u4e00-\u9fff]", item.title)
            or not re.search(r"[\u4e00-\u9fff]", item.content)
        )
    ]
    if not untranslated:
        return False

    payload = [
        {"id": item.id, "title": item.title, "summary": " ".join(item.content.split())[:220]}
        for item in untranslated
    ]
    try:
        content, _ = _chat(
            settings,
            "你是严谨的中英新闻翻译编辑。仅翻译给出的标题和简介，不得添加或删除事实、数据、专有名词或链接。"
            "返回严格 JSON 数组，不要 Markdown。每项仅含 id、title、summary，id 必须与输入一致；title 和 summary 必须使用简体中文。",
            "请翻译以下来源预览：\n" + json.dumps(payload, ensure_ascii=False),
        )
    except Exception:
        return False

    translations = _parse_translations(content)
    changed = False
    for item in untranslated:
        translation = translations.get(item.id)
        if not translation:
            continue
        item.raw_json = {**(item.raw_json or {}), "dashboard_zh": translation}
        changed = True
    return changed


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
