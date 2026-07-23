from fastapi.testclient import TestClient

from app.database import SessionLocal
from app import main as main_module
from app.main import app
from app.models import Draft, Topic


def test_application_serves_health_check_and_dashboard() -> None:
    with TestClient(app) as client:
        health_response = client.get("/health")
        dashboard_response = client.get("/")

    assert health_response.status_code == 200
    assert health_response.json()["status"] == "ok"
    assert dashboard_response.status_code == 200
    assert "AI Radar" in dashboard_response.text


def test_topic_detail_draft_save_and_markdown_export() -> None:
    with TestClient(app) as client:
        with SessionLocal() as session:
            topic = session.query(Topic).first()
            draft = session.query(Draft).filter(Draft.topic_id == topic.id).first()
            draft_id = draft.id
            original_title = draft.title
            original_content = draft.content_markdown

        detail_response = client.get(f"/topics/{topic.id}")
        save_response = client.post(
            f"/drafts/{draft_id}",
            data={
                "title": "阶段二测试草稿",
                "content_markdown": "这是一段用于验证保存和导出的 Markdown 正文。",
                "mode": "编辑解读",
                "image_prompt": "简洁的 AI 科技资讯插画",
            },
            headers={"HX-Request": "true"},
        )
        export_response = client.get(f"/drafts/{draft_id}/export")
        empty_response = client.get("/topics/fragment", params={"keyword": "不存在的关键词"})

        assert detail_response.status_code == 200
        assert "来源证据" in detail_response.text
        assert save_response.status_code == 200
        assert "草稿已保存" in save_response.text
        assert export_response.status_code == 200
        assert "阶段二测试草稿" in export_response.text
        assert "没有匹配的话题" in empty_response.text

        with SessionLocal() as session:
            draft = session.get(Draft, draft_id)
            draft.title = original_title
            draft.content_markdown = original_content
            session.commit()


def test_manual_collection_endpoint_returns_immediately(monkeypatch) -> None:
    calls: list[object] = []

    def fake_collect(*args: object) -> None:
        calls.append(args)

    monkeypatch.setattr(main_module, "collect_sources", fake_collect)

    with TestClient(app) as client:
        response = client.post("/collection/run")
        status_response = client.get("/collection/status")

    assert response.status_code == 200
    assert "采集任务已开始" in response.text
    assert status_response.status_code == 200
    assert calls
