from datetime import datetime, timezone

from app.config import Settings
from app.models import SourceItem, Topic, TopicEvidence
from app.services import intelligence
from app.services.intelligence import LocalEvidenceIntelligence, OpenAIModelValidationError, validate_openai_model_access


def test_local_evidence_analysis_marks_data_sources_at_the_end() -> None:
    now = datetime.now(timezone.utc)
    source = SourceItem(
        id=1,
        platform="测试公开来源",
        external_id="test-source",
        title="AI agent reasoning benchmark",
        content="公开 benchmark 摘要。",
        url="https://example.com/ai-agent",
        author="测试作者",
        published_at=now,
        fetched_at=now,
        metrics_json={},
        language="en",
        raw_json={},
    )
    topic = Topic(
        id=1,
        title="测试 AI 话题",
        summary="测试摘要",
        heat_score=90,
        freshness="近 24 小时",
        latest_published_at=now,
        status="active",
    )
    evidence = TopicEvidence(topic_id=1, source_item_id=1, relevance_score=1.0)
    evidence.source_item = source
    topic.evidences = [evidence]

    result = LocalEvidenceIntelligence().analyze_evidence(topic)

    assert result.provider_name.startswith("本地规则分析")
    assert "## 数据来源" in result.content_markdown
    assert result.content_markdown.rstrip().endswith("https://example.com/ai-agent)（测试作者，2026-07-23）")


def test_model_validation_skips_openai_when_api_key_is_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        intelligence,
        "OpenAIIntelligence",
        lambda *_: (_ for _ in ()).throw(AssertionError("OpenAI client should not be created")),
    )

    validate_openai_model_access(Settings(openai_api_key=None))


def test_model_validation_reports_model_access_errors(monkeypatch) -> None:
    class FailingModels:
        def retrieve(self, model: str) -> None:
            assert model == "gpt-5.5"
            raise RuntimeError("model_not_found")

    class FailingProvider:
        def __init__(self, api_key: str, model: str) -> None:
            assert api_key == "test-key"
            assert model == "gpt-5.5"
            self.client = type("Client", (), {"models": FailingModels()})()

    monkeypatch.setattr(intelligence, "OpenAIIntelligence", FailingProvider)

    try:
        validate_openai_model_access(Settings(openai_api_key="test-key", openai_model="gpt-5.5"))
    except OpenAIModelValidationError as error:
        assert "OPENAI_MODEL='gpt-5.5'" in str(error)
        assert "API 项目" in str(error)
    else:
        raise AssertionError("Expected a model-access validation error")
