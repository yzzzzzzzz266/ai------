from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app import main as main_module
from app.database import SessionLocal
from app.main import app
from app.models import Draft, ResearchArtifact, SourceItem, Topic, TopicEvidence


def create_topic_fixture() -> tuple[int, int, int]:
    suffix = uuid4().hex
    now = datetime.now(timezone.utc)
    with SessionLocal() as session:
        source = SourceItem(
            platform="测试公开来源",
            external_id=f"test-{suffix}",
            title="AI agent 前沿测试来源",
            content="这是一条关于 AI agent reasoning benchmark 的公开测试摘要。",
            url=f"https://example.com/{suffix}",
            author="测试作者",
            published_at=now,
            fetched_at=now,
            metrics_json={},
            language="zh",
            raw_json={"test": True},
        )
        topic = Topic(
            title=f"测试前沿 AI 话题 {suffix}",
            summary="用于路由测试的公开来源话题。",
            heat_score=80,
            freshness="近 24 小时",
            latest_published_at=now,
            status="active",
        )
        session.add_all([source, topic])
        session.flush()
        session.add(TopicEvidence(topic_id=topic.id, source_item_id=source.id, relevance_score=1))
        draft = Draft(
            topic_id=topic.id,
            mode="新闻快讯",
            title="测试草稿",
            content_markdown=f"[测试公开来源]({source.url})\n\n这是一项重大突破。",
            image_prompt="AI 新闻插画",
            editor_params_json={},
            created_at=now,
            updated_at=now,
        )
        session.add(draft)
        session.commit()
        return topic.id, source.id, draft.id


def remove_topic_fixture(topic_id: int, source_id: int) -> None:
    with SessionLocal() as session:
        session.query(ResearchArtifact).filter(ResearchArtifact.topic_id == topic_id).delete()
        session.query(ResearchArtifact).filter(ResearchArtifact.source_item_id == source_id).delete()
        topic = session.get(Topic, topic_id)
        if topic:
            session.delete(topic)
        source = session.get(SourceItem, source_id)
        if source:
            session.delete(source)
        session.commit()


def test_application_serves_health_check_and_dashboard() -> None:
    with TestClient(app) as client:
        health_response = client.get("/health")
        dashboard_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert "intelligence_provider" in health_response.json()
    assert dashboard_response.status_code == 200
    assert "AI Radar" in dashboard_response.text


def test_topic_draft_and_export_routes() -> None:
    topic_id, source_id, draft_id = create_topic_fixture()
    try:
        with TestClient(app) as client:
            detail_response = client.get(f"/topics/{topic_id}")
            save_response = client.post(
                f"/drafts/{draft_id}",
                data={"title": "已保存草稿", "content_markdown": "[来源](https://example.com)\n\nAI agent 摘要。", "mode": "编辑解读", "image_prompt": "AI 新闻插画"},
                headers={"HX-Request": "true"},
            )
            export_response = client.get(f"/drafts/{draft_id}/export")
            empty_response = client.get("/topics/fragment", params={"keyword": "不存在的关键词"})

        assert detail_response.status_code == 200
        assert "AI 读新闻" in detail_response.text
        assert save_response.status_code == 200
        assert "草稿已保存" in save_response.text
        assert export_response.status_code == 200
        assert "已保存草稿" in export_response.text
        assert "没有匹配的话题" in empty_response.text
    finally:
        remove_topic_fixture(topic_id, source_id)


def test_manual_collection_and_aggregation_endpoints(monkeypatch) -> None:
    collection_calls: list[object] = []
    aggregation_calls: list[bool] = []
    monkeypatch.setattr(main_module, "collect_sources", lambda *args: collection_calls.append(args))
    monkeypatch.setattr(main_module, "run_topic_aggregation", lambda: aggregation_calls.append(True))

    with TestClient(app) as client:
        collection_response = client.post("/collection/run")
        aggregation_response = client.post("/topics/aggregate")

    assert collection_response.status_code == 200
    assert "采集任务已开始" in collection_response.text
    assert aggregation_response.status_code == 200
    assert "热点聚合任务已开始" in aggregation_response.text
    assert collection_calls
    assert aggregation_calls


def test_generation_editorial_and_ai_workspace_routes() -> None:
    topic_id, source_id, draft_id = create_topic_fixture()
    try:
        with TestClient(app) as client:
            generation_page = client.get(f"/topics/{topic_id}/drafts/generate")
            draft_response = client.post(
                f"/topics/{topic_id}/drafts/generate",
                data={"mode": "技术拆解", "audience": "开发者", "writing_style": "技术说明", "stance": "谨慎分析", "target_length": "自动", "banned_words": "", "required_facts": "AI", "avoided_angles": ""},
                follow_redirects=False,
            )
            review_response = client.get(f"/drafts/{draft_id}/review")
            rewrite_response = client.post(f"/drafts/{draft_id}/rewrite", data={"rewrite_mode": "更克制"}, follow_redirects=False)
            workspace_response = client.get(f"/topics/{topic_id}/ai-workspace")
            analysis_response = client.post(f"/topics/{topic_id}/ai-workspace", data={"task_kind": "evidence_analysis"}, follow_redirects=False)
            read_response = client.post(f"/sources/{source_id}/read", follow_redirects=False)

        assert generation_page.status_code == 200
        assert draft_response.status_code == 303
        assert review_response.status_code == 200
        assert rewrite_response.status_code == 303
        assert workspace_response.status_code == 200
        assert analysis_response.status_code == 303
        assert read_response.status_code == 303
    finally:
        remove_topic_fixture(topic_id, source_id)
