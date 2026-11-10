import xml.etree.ElementTree as ElementTree
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import Base
from app.models import CollectionRun, ResearchArtifact, SourceItem, Topic, TopicEvidence
from app.services import collection
from app.services.collection import (
    ArxivAdapter,
    IthomeAdapter,
    JuejinAdapter,
    RssAdapter,
    SourceItemPayload,
    build_adapters,
    collect_sources,
    is_ai_related,
    persist_items,
    purge_expired_source_items,
)


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


def test_ithome_adapter_labels_rss_items_with_its_platform() -> None:
    xml = b"""<rss><channel><item><guid>123</guid><title>AI agent update</title><link>https://www.ithome.com/0/1/123.htm</link><description>AI model release</description><pubDate>Sat, 01 Aug 2026 10:00:00 +0000</pubDate></item></channel></rss>"""
    response = httpx.Response(
        200,
        content=xml,
        request=httpx.Request("GET", "https://www.ithome.com/rss/"),
    )

    class FakeClient:
        def get(self, url: str) -> httpx.Response:
            assert url == "https://www.ithome.com/rss/"
            return response

    items = IthomeAdapter("https://www.ithome.com/rss/").fetch(FakeClient())

    assert [(item.platform, item.external_id) for item in items] == [("IT之家", "123")]


def test_juejin_adapter_maps_public_recommendation_records() -> None:
    response = httpx.Response(
        200,
        json={
            "data": [
                {
                    "item_info": {
                        "article_info": {
                            "article_id": "article-1",
                            "title": "AI agent workflow",
                            "brief_content": "AI model release details",
                            "ctime": "1785578400",
                            "digg_count": 4,
                            "comment_count": 2,
                        },
                        "author_user_info": {"user_name": "juejin-author"},
                    }
                }
            ]
        },
        request=httpx.Request(
            "POST",
            "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed",
        ),
    )

    class FakeClient:
        def post(self, url: str, json: dict[str, int | str]) -> httpx.Response:
            assert url == "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
            assert json == {"id_type": 2, "sort_type": 200, "cursor": "0", "limit": 20}
            return response

    items = JuejinAdapter("https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed").fetch(FakeClient())

    assert [(item.platform, item.external_id, item.url) for item in items] == [
        ("稀土掘金", "article-1", "https://juejin.cn/post/article-1")
    ]


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


def test_purge_expired_source_items_deletes_old_data_and_its_references() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(timezone.utc)

    with Session(engine) as session:
        old_item = SourceItem(
            platform="test",
            external_id="old",
            title="Old AI agent release",
            content="",
            url="https://example.com/old",
            published_at=now - timedelta(days=7, seconds=1),
            fetched_at=now,
            metrics_json={},
            language="en",
            raw_json={},
        )
        retained_item = SourceItem(
            platform="test",
            external_id="retained",
            title="Retained AI agent release",
            content="",
            url="https://example.com/retained",
            published_at=now - timedelta(days=6),
            fetched_at=now,
            metrics_json={},
            language="en",
            raw_json={},
        )
        topic = Topic(
            title="Test topic",
            summary="",
            latest_published_at=now,
        )
        session.add_all([old_item, retained_item, topic])
        session.flush()
        session.add(TopicEvidence(topic_id=topic.id, source_item_id=old_item.id))
        session.add(
            ResearchArtifact(
                source_item_id=old_item.id,
                kind="summary",
                title="Old item analysis",
                content_markdown="",
                provider_name="test",
                source_urls_json=[],
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        deleted_count = purge_expired_source_items(session, retention_days=7)

        assert deleted_count == 1
        assert session.scalar(select(func.count(SourceItem.id))) == 1
        assert session.scalar(select(func.count(TopicEvidence.id))) == 0
        assert session.scalar(select(func.count(ResearchArtifact.id))) == 0
        assert session.get(Topic, topic.id) is not None


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
