from fastapi.testclient import TestClient

from app.database import SessionLocal
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
