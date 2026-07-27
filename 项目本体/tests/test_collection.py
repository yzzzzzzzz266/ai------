import xml.etree.ElementTree as ElementTree
from datetime import datetime, timezone

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import Base
from app.models import CollectionRun, SourceItem
from app.services import collection
from app.services.collection import ArxivAdapter, RssAdapter, SourceItemPayload, build_adapters, collect_sources, is_ai_related, persist_items


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

        generic_ai = SourceItemPayload(
            **{
                **make_payload("AI 行业简报", "https://example.com/generic-ai").__dict__,
                "content": "artificial intelligence 的一般性内容",
            }
        )
        first_stats = persist_items(session, [source, irrelevant, generic_ai])
        second_stats = persist_items(session, [source])

        assert first_stats.added_count == 1
        assert first_stats.filtered_count == 2
        assert second_stats.duplicate_count == 1
        assert session.scalar(select(func.count(SourceItem.id))) == 1


def test_persist_items_normalizes_and_deduplicates_urls_within_one_batch() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        original = make_payload("AI agent release", "\nhttps://example.com/agent-release\n", "\nrelease-1\n")
        duplicate = SourceItemPayload(**{**original.__dict__, "url": "https://example.com/agent-release"})

        stats = persist_items(session, [original, duplicate])
        saved_item = session.scalar(select(SourceItem))

        assert stats.added_count == 1
        assert stats.duplicate_count == 1
        assert saved_item.url == "https://example.com/agent-release"
        assert saved_item.external_id == "release-1"


def test_rss_adapter_strips_whitespace_from_guid_links() -> None:
    entry = ElementTree.fromstring(
        "<item><title>AI agent release</title><guid>\nhttps://example.com/rss-agent\n</guid>"
        "<description>AI agent release details</description><pubDate>Wed, 01 Jan 2025 00:00:00 GMT</pubDate></item>"
    )

    payload = RssAdapter(["https://example.com/feed.xml"])._payload_from_entry(entry, "https://example.com/feed.xml")

    assert payload is not None
    assert payload.url == "https://example.com/rss-agent"
    assert payload.external_id == "https://example.com/rss-agent"


def test_rss_adapter_skips_entries_without_a_parseable_publish_time() -> None:
    entry = ElementTree.fromstring(
        "<item><title>AI agent release</title><guid>https://example.com/rss-agent</guid>"
        "<description>AI agent release details</description></item>"
    )

    payload = RssAdapter(["https://example.com/feed.xml"])._payload_from_entry(entry, "https://example.com/feed.xml")

    assert payload is None


def test_ai_keyword_matching_does_not_treat_aiib_or_capital_as_ai_api() -> None:
    item = SourceItemPayload(
        **{
            **make_payload("AIIB loans for capital conversion", "https://example.com/aiib", "aiib-1").__dict__,
            "content": "The bank announced a capital investment for coal-to-gas conversion.",
        }
    )

    assert not is_ai_related(item)


def test_persist_items_skips_items_older_than_the_collection_window() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    old_item = SourceItemPayload(
        **{
            **make_payload("AI agent release", "https://example.com/old-agent", "old-agent").__dict__,
            "published_at": datetime.now(timezone.utc).replace(year=2025),
        }
    )

    with Session(engine) as session:
        stats = persist_items(session, [old_item], max_item_age_days=7)

        assert stats.filtered_count == 1
        assert session.scalar(select(func.count(SourceItem.id))) == 0


def test_authority_source_adapters_are_enabled_only_when_configured() -> None:
    base_names = [adapter.name for adapter in build_adapters(Settings())]
    authority_names = [
        adapter.name
        for adapter in build_adapters(
            Settings(x_bearer_token="test-token", x_author_usernames="openai, frontier_lab", bilibili_author_mids="123,456")
        )
    ]

    assert "X" not in base_names
    assert "Bilibili" not in base_names
    assert "X" in authority_names
    assert "Bilibili" in authority_names


def test_rss_adapter_accepts_comma_and_newline_separated_feeds() -> None:
    adapters = build_adapters(
        Settings(
            rss_urls=(
                "https://openai.com/news/rss.xml,https://deepmind.google/blog/rss.xml\n"
                "https://blog.csdn.net/linshantang/rss/list"
            )
        )
    )
    rss_adapter = next(adapter for adapter in adapters if adapter.name == "RSS")

    assert rss_adapter.feed_urls == [
        "https://openai.com/news/rss.xml",
        "https://deepmind.google/blog/rss.xml",
        "https://blog.csdn.net/linshantang/rss/list",
    ]


def test_rss_adapter_skips_a_failed_feed_and_keeps_other_feed_items() -> None:
    failed_url = "https://blog.csdn.net/sinat_39620217/rss/list"
    working_url = "https://example.com/working.xml"

    class FakeClient:
        def get(self, url: str) -> httpx.Response:
            request = httpx.Request("GET", url)
            if url == failed_url:
                return httpx.Response(521, request=request)
            return httpx.Response(
                200,
                content=b"""<rss><channel><item><guid>working-1</guid><title>AI agent update</title><link>https://example.com/post</link><pubDate>Sat, 25 Jul 2026 10:00:00 +0000</pubDate></item></channel></rss>""",
                request=request,
            )

    items = RssAdapter([failed_url, working_url]).fetch(FakeClient())

    assert [item.external_id for item in items] == ["working-1"]
    assert [item.metrics_json["feed_url"] for item in items] == [working_url]


def test_arxiv_adapter_retries_once_after_rate_limit(monkeypatch) -> None:
    xml = b"""<feed xmlns=\"http://www.w3.org/2005/Atom\"><entry><id>https://arxiv.org/abs/1234.5678</id><title>AI agent benchmark</title><summary>Machine learning research</summary><author><name>Test Author</name></author><published>2026-07-27T00:00:00Z</published></entry></feed>"""
    responses = [httpx.Response(429, headers={"Retry-After": "0"}), httpx.Response(200, content=xml)]

    class FakeClient:
        def get(self, _url: str, params: dict[str, str]) -> httpx.Response:
            response = responses.pop(0)
            response.request = httpx.Request("GET", "https://export.arxiv.org/api/query", params=params)
            return response

    delays: list[float] = []
    clock = [0.0]

    def advance_clock(seconds: float) -> None:
        delays.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(collection, "_arxiv_last_request_at", -collection.ARXIV_MIN_REQUEST_INTERVAL_SECONDS)
    monkeypatch.setattr(collection.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(collection.time, "sleep", advance_clock)

    items = ArxivAdapter().fetch(FakeClient())

    assert len(items) == 1
    assert items[0].external_id == "1234.5678"
    assert delays == [collection.ARXIV_MIN_REQUEST_INTERVAL_SECONDS]


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
