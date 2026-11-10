from __future__ import annotations

import base64
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import PROJECT_DIR, Settings
from app.models import SourceItem


CONTENT_PLATFORMS = {
    "小红书": "标题必须不超过 20 个字符，不加话题标签；开头直接给出读者收益，分段短、口语化、克制地使用表情符号，并在结尾给出可讨论的问题。",
    "微信公众号": "适合公众号阅读：标题明确，段落有层次，先交代事实再解释影响，避免夸张标题党。",
    "知乎": "以问题意识和论证结构展开，解释背景、证据和限制，结尾给出可供讨论的判断。",
    "微博": "简洁、信息密度高，先概括最新进展，再列出两到三项关键事实和来源。",
    "通用": "采用专业、清晰且适合公开发布的中文表达。",
}


class CreativeGenerationError(RuntimeError):
    pass


MAX_GENERATED_IMAGE_BYTES = 20 * 1024 * 1024
XIAOHONGSHU_TITLE_MAX_LENGTH = 20
IMAGE_GENERATION_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class CreatorDraft:
    title: str
    content_markdown: str
    image_prompt: str
    provider_name: str


def rewrite_creator_draft(
    settings: Settings,
    *,
    title: str,
    content_markdown: str,
    image_prompt: str,
    platform: str,
    instructions: str,
    editor_parameters: dict[str, object],
) -> CreatorDraft:
    """Rework an existing draft without treating it as a source of new facts."""
    if not title.strip() or not content_markdown.strip():
        raise CreativeGenerationError("请先填写标题和正文后再使用 AI 重新编写。")

    selected_platform = platform if platform in CONTENT_PLATFORMS else "通用"
    system_prompt = (
        "你是一名严谨的中文科技新闻编辑。你只能依据输入草稿中已经出现且可追溯的事实、数字、引语、"
        "时间、机构名称和 Markdown 来源链接进行重写；不得补充外部知识、猜测、评价或无来源细节。"
        "必须保留原文中的全部 Markdown 来源链接，且不得修改链接地址。"
        "输出严格 JSON，不要 Markdown 代码块，字段为 title、content_markdown、image_prompt。"
        "title 是克制、信息明确的中文新闻标题；content_markdown 使用清晰的小标题、短段落和必要列表；"
        "image_prompt 使用英文，保留原意且不含文字、logo 或品牌标识。"
    )
    if selected_platform == "微信公众号":
        system_prompt += (
            "微信公众号写作要求：以技术新闻稿的编辑标准重组内容。开头用一段交代主体、动作、时间和"
            "直接影响；随后按“发生了什么、技术上有什么变化、证据与限制、对开发者或行业意味着什么”的"
            "顺序展开。技术部分需具体说明模型、架构、接口、性能指标、开源许可、部署条件或实验设置，"
            "但仅限原文已有信息；没有细节时明确写“现有资料未披露”。区分已确认事实、官方声明与分析判断，"
            "避免“颠覆”“爆发”“遥遥领先”“必然”等夸张词，也不写煽动性导语、投资建议或无根据的前景判断。"
            "结尾用一段简短说明仍待验证的问题或后续观察点，不虚构结论。"
        )

    parameters = "\n".join(
        f"{label}：{editor_parameters.get(key) or '未设置'}"
        for key, label in (
            ("audience", "目标读者"),
            ("writing_style", "文风"),
            ("stance", "立场强度"),
            ("target_length", "目标长度"),
            ("banned_words", "禁用词"),
            ("required_facts", "必须出现的事实或来源"),
            ("avoided_angles", "必须避免的角度"),
        )
    )
    user_prompt = (
        f"发布平台：{selected_platform}\n平台写作要求：{CONTENT_PLATFORMS[selected_platform]}\n"
        f"编辑参数：\n{parameters}\n\n用户补充要求：{instructions.strip() or '无'}\n\n"
        f"当前标题：{title.strip()}\n\n当前正文（保留其中全部来源链接）：\n{content_markdown.strip()}\n\n"
        f"当前配图提示词：{image_prompt.strip() or '无'}"
    )
    content, provider_name = _chat(settings, system_prompt, user_prompt)
    result = _json_result(content)
    missing_links = set(re.findall(r"\[[^\]]+\]\([^\)]+\)", content_markdown)) - set(
        re.findall(r"\[[^\]]+\]\([^\)]+\)", result["content_markdown"])
    )
    if missing_links:
        raise CreativeGenerationError("AI 重写结果缺少原有来源链接，请重试。")
    result["title"] = _platform_title(result["title"], selected_platform)
    return CreatorDraft(provider_name=provider_name, **result)


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


def _platform_title(title: str, platform: str) -> str:
    if platform != "小红书":
        return title
    compact_title = re.sub(r"\s+", "", title)
    shortened_title = compact_title[:XIAOHONGSHU_TITLE_MAX_LENGTH].rstrip("，。！？、:：；;")
    return shortened_title or compact_title[:XIAOHONGSHU_TITLE_MAX_LENGTH]


def generate_creator_draft(settings: Settings, items: list[SourceItem], platform: str, instructions: str) -> CreatorDraft:
    if not items:
        raise CreativeGenerationError("请至少选择一条来源后再生成草稿。")
    selected_platform = platform if platform in CONTENT_PLATFORMS else "通用"
    system_prompt = (
        "你是严谨的中文内容编辑和视觉提示词策划。只能使用用户给出的来源事实，不得补写未证实数据、引语或结论。"
        "输出严格 JSON，不要 Markdown 代码块，字段为 title、content_markdown、image_prompt。"
        "content_markdown 必须包含“## 来源”小节，列出实际使用的来源链接；image_prompt 使用英文，采用简洁配图：一个明确主体、干净背景、最多三种辅助视觉元素。"
        "避免拼贴、多面板界面、密集数据流和复杂叙事；禁止文字、logo、品牌标识。"
    )
    user_prompt = (
        f"发布平台：{selected_platform}\n平台写作要求：{CONTENT_PLATFORMS[selected_platform]}\n"
        f"用户修改要求：{instructions.strip() or '无额外要求。'}\n\n"
        f"选定来源：\n{_source_context(items)}"
    )
    content, provider_name = _chat(settings, system_prompt, user_prompt)
    result = _json_result(content)
    result["title"] = _platform_title(result["title"], selected_platform)
    return CreatorDraft(provider_name=provider_name, **result)


def _refine_image_prompt(settings: Settings, image_prompt: str, adjustment: str) -> tuple[str, str]:
    if not adjustment.strip():
        _, _, provider_name = _chat_client(settings)
        return image_prompt.strip(), provider_name
    content, provider_name = _chat(
        settings,
        "You are an image prompt editor. Return only one concise English image-generation prompt, under 320 characters."
        "Use one clear subject, a minimal background, and at most three supporting visual elements. Avoid collage layouts, busy dashboards, dense data streams, or multiple scenes."
        "Never include text, logos, trademarks, or brand names.",
        f"Current prompt:\n{image_prompt}\n\nUser requested changes:\n{adjustment}",
    )
    return content[:320].strip(), provider_name


def _download_image(image_url: str) -> bytes:
    parsed_url = urlparse(image_url)
    if parsed_url.scheme not in {"http", "https"}:
        raise CreativeGenerationError("图像 API 返回了不支持的图片地址。")
    try:
        response = httpx.get(image_url, follow_redirects=True, timeout=30.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise CreativeGenerationError(f"无法下载图像 API 返回的图片：{error}") from error
    image_bytes = response.content
    if not image_bytes or len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise CreativeGenerationError("图像 API 返回的图片为空或超过 20 MB。")
    content_type = response.headers.get("content-type", "").lower()
    if content_type and not content_type.startswith("image/"):
        raise CreativeGenerationError("图像 API 返回的地址不是图片内容。")
    return image_bytes


def _image_bytes_from_response(image_data: object) -> bytes:
    image_b64 = getattr(image_data, "b64_json", None)
    if image_b64:
        try:
            image_bytes = base64.b64decode(image_b64, validate=True)
        except (ValueError, TypeError) as error:
            raise CreativeGenerationError("图像 API 返回的 Base64 图片数据无效。") from error
        if not image_bytes or len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
            raise CreativeGenerationError("图像 API 返回的图片为空或超过 20 MB。")
        return image_bytes
    image_url = getattr(image_data, "url", None)
    if isinstance(image_url, str) and image_url.strip():
        return _download_image(image_url.strip())
    raise CreativeGenerationError("图像 API 未返回可保存的图片数据。")


def _is_retryable_image_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    return status_code in {408, 409, 429} or (isinstance(status_code, int) and status_code >= 500) or error.__class__.__name__ in {
        "APIConnectionError",
        "APITimeoutError",
    }


def _image_error_message(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    if isinstance(status_code, int):
        return f"图像生成失败：上游图像服务返回 HTTP {status_code}。"
    if error.__class__.__name__ in {"APIConnectionError", "APITimeoutError"}:
        return "图像生成失败：无法连接上游图像服务或请求超时。"
    return "图像生成失败：上游图像服务返回了无法处理的响应。"


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
    for attempt in range(IMAGE_GENERATION_MAX_ATTEMPTS):
        try:
            response = client.images.generate(model=settings.image_model, prompt=final_prompt, size=settings.image_size)
            image_data = response.data[0]
            image_bytes = _image_bytes_from_response(image_data)
            break
        except CreativeGenerationError:
            raise
        except Exception as error:
            if _is_retryable_image_error(error) and attempt < IMAGE_GENERATION_MAX_ATTEMPTS - 1:
                time.sleep(2**attempt)
                continue
            raise CreativeGenerationError(_image_error_message(error)) from error
    output_dir = PROJECT_DIR / "app" / "static" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"draft-{uuid.uuid4().hex}.png"
    (output_dir / filename).write_bytes(image_bytes)
    return final_prompt, f"/static/generated/{filename}", text_provider
