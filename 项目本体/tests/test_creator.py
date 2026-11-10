from types import SimpleNamespace
from datetime import datetime, timezone
import json

import pytest

from app.config import Settings
from app.services import creator


def test_image_response_accepts_base64_data() -> None:
    image_data = SimpleNamespace(b64_json="aGVsbG8=", url=None)

    assert creator._image_bytes_from_response(image_data) == b"hello"


def test_image_response_downloads_url_when_base64_is_absent(monkeypatch) -> None:
    response = SimpleNamespace(content=b"image-bytes", headers={"content-type": "image/png"})
    response.raise_for_status = lambda: None
    monkeypatch.setattr(creator.httpx, "get", lambda *args, **kwargs: response)

    image_data = SimpleNamespace(b64_json=None, url="https://images.example.com/generated.png")

    assert creator._image_bytes_from_response(image_data) == b"image-bytes"


def test_image_response_rejects_non_image_download(monkeypatch) -> None:
    response = SimpleNamespace(content=b"not an image", headers={"content-type": "text/html"})
    response.raise_for_status = lambda: None
    monkeypatch.setattr(creator.httpx, "get", lambda *args, **kwargs: response)

    with pytest.raises(creator.CreativeGenerationError, match="不是图片内容"):
        creator._image_bytes_from_response(SimpleNamespace(b64_json=None, url="https://images.example.com/error"))


def test_image_prompt_refinement_requests_a_simple_composition(monkeypatch) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        creator,
        "_chat",
        lambda _settings, system_prompt, _user_prompt: (captured.setdefault("prompt", system_prompt) and "simple prompt", "test"),
    )

    prompt, _ = creator._refine_image_prompt(Settings(), "busy dashboard with many panels", "use a softer style")

    assert prompt == "simple prompt"
    assert "one clear subject" in captured["prompt"]
    assert "Avoid collage layouts" in captured["prompt"]


def test_image_generation_retries_only_transient_upstream_errors() -> None:
    class UpstreamError(Exception):
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    assert creator._is_retryable_image_error(UpstreamError(429))
    assert creator._is_retryable_image_error(UpstreamError(503))
    assert not creator._is_retryable_image_error(UpstreamError(400))


def test_xiaohongshu_creator_title_is_limited_to_twenty_characters(monkeypatch) -> None:
    source = SimpleNamespace(
        id=1,
        platform="RSS",
        title="AI agent release",
        author="Test author",
        published_at=datetime.now(timezone.utc),
        url="https://example.com/source",
        content="AI agent update",
    )
    long_title = "这是一个超过二十个字符的小红书标题需要被截短"
    monkeypatch.setattr(
        creator,
        "_chat",
        lambda *_args: (json.dumps({"title": long_title, "content_markdown": "正文", "image_prompt": "simple image"}), "test"),
    )

    draft = creator.generate_creator_draft(Settings(), [source], "小红书", "")

    assert len(draft.title) == 20
    assert draft.title == long_title[:20]


def test_wechat_ai_rewrite_uses_technical_news_requirements(monkeypatch) -> None:
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        creator,
        "_chat",
        lambda _settings, system_prompt, _user_prompt: (
            captured.setdefault("prompt", system_prompt) and json.dumps({"title": "技术新闻", "content_markdown": "正文 [来源](https://example.com)", "image_prompt": "simple image"}),
            "test",
        ),
    )

    draft = creator.rewrite_creator_draft(
        Settings(), title="旧标题", content_markdown="原文 [来源](https://example.com)", image_prompt="image", platform="微信公众号", instructions="", editor_parameters={},
    )

    assert draft.title == "技术新闻"
    assert "技术新闻稿的编辑标准" in captured["prompt"]
    assert "现有资料未披露" in captured["prompt"]
