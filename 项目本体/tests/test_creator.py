from types import SimpleNamespace

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
