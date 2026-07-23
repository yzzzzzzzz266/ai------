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


def test_topic_generation_page_and_background_aggregation(monkeypatch) -> None:
    aggregation_calls: list[bool] = []
    monkeypatch.setattr(main_module, "run_topic_aggregation", lambda: aggregation_calls.append(True))

    with TestClient(app) as client:
        with SessionLocal() as session:
            topic = session.query(Topic).first()
            topic_id = topic.id

        generation_page = client.get(f"/topics/{topic_id}/drafts/generate")
        aggregation_response = client.post("/topics/aggregate")
        generation_response = client.post(
            f"/topics/{topic_id}/drafts/generate",
            data={
                "mode": "技术拆解",
                "audience": "开发者",
                "writing_style": "技术说明",
                "stance": "谨慎分析",
                "target_length": "1,000–1,500 字",
                "banned_words": "爆发",
                "required_facts": "AI",
                "avoided_angles": "不做投资建议",
            },
            follow_redirects=False,
        )

        with SessionLocal() as session:
            generated_draft = session.query(Draft).order_by(Draft.id.desc()).first()
            generated_draft_id = generated_draft.id
            generated_content = generated_draft.content_markdown
            generated_parameters = generated_draft.editor_params_json
            session.delete(generated_draft)
            session.commit()

    assert generation_page.status_code == 200
    assert "生成可编辑草稿" in generation_page.text
    assert aggregation_response.status_code == 200
    assert "热点聚合任务已开始" in aggregation_response.text
    assert aggregation_calls
    assert generation_response.status_code == 303
    assert generated_draft_id
    assert "可追溯来源" in generated_content
    assert generated_parameters["audience"] == "开发者"


def test_editorial_review_and_rewrite_routes() -> None:
    with TestClient(app) as client:
        with SessionLocal() as session:
            draft = session.query(Draft).first()
            draft_id = draft.id
            original_content = draft.content_markdown
            original_parameters = dict(draft.editor_params_json)
            draft.content_markdown = "这是一项重大突破。\n\n[测试来源](https://example.com/source)"
            session.commit()

        review_response = client.get(f"/drafts/{draft_id}/review")
        rewrite_response = client.post(
            f"/drafts/{draft_id}/rewrite",
            data={"rewrite_mode": "更克制"},
            follow_redirects=False,
        )

        with SessionLocal() as session:
            draft = session.get(Draft, draft_id)
            rewritten_content = draft.content_markdown
            draft.content_markdown = original_content
            draft.editor_params_json = original_parameters
            session.commit()

    assert review_response.status_code == 200
    assert "无来源强判断" in review_response.text
    assert rewrite_response.status_code == 303
    assert "值得关注" in rewritten_content
    assert "[测试来源](https://example.com/source)" in rewritten_content
