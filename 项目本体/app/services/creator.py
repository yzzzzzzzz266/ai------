from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import PROJECT_DIR, Settings
from app.models import SourceItem


CONTENT_PLATFORMS = {
    "小红书": "开头直接给出读者收益，分段短、口语化、克制地使用表情符号，并在结尾给出可讨论的问题。",
    "微信公众号": "适合公众号阅读：标题明确，段落有层次，先交代事实再解释影响，避免夸张标题党。",
    "知乎": "以问题意识和论证结构展开，解释背景、证据和限制，结尾给出可供讨论的判断。",
    "微博": "简洁、信息密度高，先概括最新进展，再列出两到三项关键事实和来源。",
    "通用": "采用专业、清晰且适合公开发布的中文表达。",
}


class CreativeGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreatorDraft:
    title: str
    content_markdown: str
    image_prompt: str
    provider_name: str


def _chat_client(settings: Settings):
    from openai import OpenAI

    provider = settings.ai_provider.strip().casefold()
    if provider in {"deepseek", "auto"} and settings.deepseek_api_key:
        return OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url), settings.deepseek_model, f"DeepSeek · {settings.deepseek_model}"
    if provider in {"openai", "auto"} and settings.openai_api_key:
        return OpenAI(api_key=settings.openai_api_key), settings.openai_model, f"OpenAI · {settings.openai_model}"
    raise CreativeGenerationError("未配置可用的 DeepSeek 或 OpenAI 文本模型，无法生成创作草稿。")


def _chat(settings: Settings, system_prompt: str, user_prompt: str) -> tuple[str, str]:
    client, model, provider_name = _chat_client(settings)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        temperature=0.6,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise CreativeGenerationError("文本模型未返回可用内容，请稍后重试。")
    return content, provider_name


def _source_context(items: list[SourceItem]) -> str:
    return "\n\n".join(
        "\n".join(
            (
                f"来源编号：{item.id}",
                f"平台：{item.platform}",
                f"标题：{item.title}",
                f"作者：{item.author or '未提供'}",
                f"发布时间：{item.published_at.strftime('%Y-%m-%d %H:%M')}",
                f"链接：{item.url}",
                f"摘要：{' '.join(item.content.split())[:1200]}",
            )
        )
        for item in items[:8]
    )


def _json_result(value: str) -> dict[str, str]:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as error:
        raise CreativeGenerationError("文本模型未按要求返回草稿结构，请重试。") from error
    if not all(isinstance(result.get(key), str) and result[key].strip() for key in ("title", "content_markdown", "image_prompt")):
        raise CreativeGenerationError("文本模型返回的草稿字段不完整，请重试。")
    return {key: result[key].strip() for key in ("title", "content_markdown", "image_prompt")}


def generate_creator_draft(settings: Settings, items: list[SourceItem], platform: str, instructions: str) -> CreatorDraft:
    if not items:
        raise CreativeGenerationError("请至少选择一条来源后再生成草稿。")
    selected_platform = platform if platform in CONTENT_PLATFORMS else "通用"
    system_prompt = (
        "你是严谨的中文内容编辑和视觉提示词策划。只能使用用户给出的来源事实，不得补写未证实数据、引语或结论。"
        "输出严格 JSON，不要 Markdown 代码块，字段为 title、content_markdown、image_prompt。"
        "content_markdown 必须包含“## 来源”小节，列出实际使用的来源链接；image_prompt 使用英文，详细描述构图、主体、光线、风格和负面限制，且禁止文字、logo、品牌标识。"
    )
    user_prompt = (
        f"发布平台：{selected_platform}\n平台写作要求：{CONTENT_PLATFORMS[selected_platform]}\n"
        f"用户修改要求：{instructions.strip() or '无额外要求。'}\n\n"
        f"选定来源：\n{_source_context(items)}"
    )
    content, provider_name = _chat(settings, system_prompt, user_prompt)
    result = _json_result(content)
    return CreatorDraft(provider_name=provider_name, **result)


def _refine_image_prompt(settings: Settings, image_prompt: str, adjustment: str) -> tuple[str, str]:
    if not adjustment.strip():
        _, _, provider_name = _chat_client(settings)
        return image_prompt.strip(), provider_name
    content, provider_name = _chat(
        settings,
        "You are an image prompt editor. Return only one detailed English image-generation prompt. Keep it under 900 characters; never include text, logos, trademarks, or brand names.",
        f"Current prompt:\n{image_prompt}\n\nUser requested changes:\n{adjustment}",
    )
    return content[:900].strip(), provider_name


def generate_draft_image(settings: Settings, image_prompt: str, adjustment: str) -> tuple[str, str, str]:
    final_prompt, text_provider = _refine_image_prompt(settings, image_prompt, adjustment)
    from openai import OpenAI

    image_key = settings.image_api_key or settings.openai_api_key
    if not image_key:
        raise CreativeGenerationError("请在 .env 配置 IMAGE_API_KEY（或可用的 OPENAI_API_KEY）后再生成图片。")
    client_options = {"api_key": image_key}
    if settings.image_base_url:
        client_options["base_url"] = settings.image_base_url
    client = OpenAI(**client_options)
    try:
        response = client.images.generate(model=settings.image_model, prompt=final_prompt, size=settings.image_size)
        image_data = response.data[0]
        if not image_data.b64_json:
            raise CreativeGenerationError("图像 API 未返回可保存的图片数据。")
        image_bytes = base64.b64decode(image_data.b64_json)
    except CreativeGenerationError:
        raise
    except Exception as error:
        raise CreativeGenerationError(f"图像生成失败：{error}") from error
    output_dir = PROJECT_DIR / "app" / "static" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"draft-{uuid.uuid4().hex}.png"
    (output_dir / filename).write_bytes(image_bytes)
    return final_prompt, f"/static/generated/{filename}", text_provider
