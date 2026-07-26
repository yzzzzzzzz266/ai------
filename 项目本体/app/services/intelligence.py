from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.config import Settings
from app.models import SourceItem, Topic


TASK_LABELS = {
    "news_read": "AI 新闻阅读",
    "research_pack": "AI 资料包",
    "evidence_analysis": "AI 证据分析",
}


@dataclass(frozen=True)
class IntelligenceResult:
    title: str
    content_markdown: str
    provider_name: str
    source_urls: list[str]


class IntelligenceProvider(Protocol):
    name: str

    def read_news(self, item: SourceItem) -> IntelligenceResult: ...

    def build_research_pack(self, topic: Topic) -> IntelligenceResult: ...

    def analyze_evidence(self, topic: Topic) -> IntelligenceResult: ...

    def summarize_topic(self, sources: list[SourceItem]) -> str | None: ...


class OpenAIModelValidationError(RuntimeError):
    """Raised when the configured API project cannot access its selected model."""


def _sentences(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", value) if part.strip()]


def _source_line(item: SourceItem) -> str:
    return f"- [{item.platform}：{item.title}]({item.url})（{item.author or '作者未提供'}，{item.published_at.strftime('%Y-%m-%d')}）"


def _topic_items(topic: Topic) -> list[SourceItem]:
    return [evidence.source_item for evidence in sorted(topic.evidences, key=lambda value: value.source_item.published_at, reverse=True)]


def _topic_summary_instructions() -> str:
    return (
        "你是严谨的中文 AI 新闻编辑。仅依据给定来源，输出恰好一句 70 到 120 字的中文热点摘要。"
        "这句话必须说清楚谁或什么发生了什么、关键进展或数据，以及为何值得关注；"
        "信息不足时明确说明，不能虚构、不能使用标题、列表、Markdown、来源链接或多句话。"
    )


def _topic_summary_context(sources: list[SourceItem]) -> str:
    return "\n\n".join(
        "\n".join(
            (
                f"平台：{item.platform}",
                f"标题：{item.title}",
                f"作者：{item.author or '未提供'}",
                f"发布时间：{item.published_at.isoformat()}",
                f"内容：{' '.join(item.content.split())[:900]}",
            )
        )
        for item in sorted(sources, key=lambda item: item.published_at, reverse=True)[:8]
    )


class LocalEvidenceIntelligence:
    name = "本地规则分析（未配置模型 API）"

    def read_news(self, item: SourceItem) -> IntelligenceResult:
        highlights = _sentences(item.content)[:3] or ["来源没有提供足够的可解析摘要。"]
        content = (
            f"## 主要内容\n\n- {item.title}\n"
            + "\n".join(f"- {highlight}" for highlight in highlights)
            + f"\n\n## AI 前沿关联\n\n该条目来自 {item.platform}，请结合原始链接确认模型、论文、仓库或产品细节。"
            + f"\n\n## 需要进一步核验\n\n- 指标、样本范围和发布时间是否完整；\n- 是否有后续更新或官方说明。\n\n## 数据来源\n\n{_source_line(item)}"
        )
        return IntelligenceResult(f"新闻阅读：{item.title}", content, self.name, [item.url])

    def build_research_pack(self, topic: Topic) -> IntelligenceResult:
        items = _topic_items(topic)
        facts = "\n".join(_source_line(item) for item in items) or "- 现有信息不足以确认。"
        titles = "；".join(item.title for item in items[:4]) or "暂无可用来源"
        content = (
            f"## 已确认资料\n\n{facts}\n\n"
            f"## 资料脉络\n\n当前话题包含 {len(items)} 条来源，重点线索包括：{titles}。\n\n"
            "## 可继续追问\n\n- 哪条来源提供了可复核的原始指标或代码？\n- 多条来源是否描述同一事件，还是相互独立的信号？\n- 哪些结论仍缺少官方公告、论文全文或复现实验支持？\n\n"
            "## 使用边界\n\n本资料包仅整理已关联来源，不将推断写成已确认事实。\n\n"
            f"## 数据来源\n\n{facts}"
        )
        return IntelligenceResult(f"资料包：{topic.title}", content, self.name, [item.url for item in items])

    def analyze_evidence(self, topic: Topic) -> IntelligenceResult:
        items = _topic_items(topic)
        fact_lines = "\n".join(_source_line(item) for item in items) or "- 现有信息不足以确认。"
        content = (
            f"## 可确认事实\n\n{fact_lines}\n\n"
            "## 谨慎推断\n\n多条来源被聚合到同一话题，说明它们在关键词或标题信号上存在重合；这不等同于已经证明长期趋势。\n\n"
            "## 未知与风险\n\n- 来源之间可能引用同一原始事件；\n- 热度指标不能直接代表技术质量；\n- 需要人工核对原始链接中的方法、版本和时间。\n\n"
            "## 建议下一步\n\n优先阅读原始论文、官方发布和仓库文档，再决定是否用于文章的核心结论。\n\n"
            f"## 数据来源\n\n{fact_lines}"
        )
        return IntelligenceResult(f"证据分析：{topic.title}", content, self.name, [item.url for item in items])

    def summarize_topic(self, sources: list[SourceItem]) -> None:
        return None


class OpenAIIntelligence:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.name = f"OpenAI · {model}"

    def _generate(self, title: str, task: str, sources: list[SourceItem]) -> IntelligenceResult:
        source_context = "\n\n".join(
            f"来源：{item.platform}\n标题：{item.title}\n作者：{item.author or '未提供'}\n时间：{item.published_at.isoformat()}\n链接：{item.url}\n摘要：{item.content}"
            for item in sources
        )
        instructions = (
            "你是严谨的中文 AI 新闻研究助理。只能使用提供的来源材料；信息不足时写明“现有信息不足以确认”。"
            "请区分可确认事实、谨慎推断和未知部分。不得虚构数据、采访、测试或来源。输出 Markdown。"
        )
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=f"任务：{task}\n标题：{title}\n\n来源材料：\n{source_context}",
        )
        source_section = "\n\n## 数据来源\n\n" + "\n".join(_source_line(item) for item in sources)
        return IntelligenceResult(title, response.output_text.strip() + source_section, self.name, [item.url for item in sources])

    def read_news(self, item: SourceItem) -> IntelligenceResult:
        return self._generate(f"新闻阅读：{item.title}", "提取主要内容、AI 前沿关联、待核验信息。", [item])

    def build_research_pack(self, topic: Topic) -> IntelligenceResult:
        return self._generate(f"资料包：{topic.title}", "整理资料脉络、核心事实、可继续追问的问题。", _topic_items(topic))

    def analyze_evidence(self, topic: Topic) -> IntelligenceResult:
        return self._generate(f"证据分析：{topic.title}", "输出可确认事实、谨慎推断、未知与风险、下一步核验建议。", _topic_items(topic))

    def summarize_topic(self, sources: list[SourceItem]) -> str:
        response = self.client.responses.create(
            model=self.model,
            instructions=_topic_summary_instructions(),
            input="请综合以下近七天来源，写热点摘要：\n\n" + _topic_summary_context(sources),
        )
        return response.output_text.strip()


class DeepSeekIntelligence:
    def __init__(self, api_key: str, model: str, base_url: str) -> None:
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.name = f"DeepSeek · {model}"

    def _generate(self, title: str, task: str, sources: list[SourceItem]) -> IntelligenceResult:
        source_context = "\n\n".join(
            f"来源：{item.platform}\n标题：{item.title}\n作者：{item.author or '未提供'}\n时间：{item.published_at.isoformat()}\n链接：{item.url}\n摘要：{item.content}"
            for item in sources
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "你是严谨的中文 AI 新闻研究助理。只能使用提供的来源材料；信息不足时明确说明。输出 Markdown，不得虚构数据、采访、测试或来源。",
                },
                {"role": "user", "content": f"任务：{task}\n标题：{title}\n\n来源材料：\n{source_context}"},
            ],
        )
        content = response.choices[0].message.content or "现有信息不足以生成有效分析。"
        source_section = "\n\n## 数据来源\n\n" + "\n".join(_source_line(item) for item in sources)
        return IntelligenceResult(title, content.strip() + source_section, self.name, [item.url for item in sources])

    def read_news(self, item: SourceItem) -> IntelligenceResult:
        return self._generate(f"新闻阅读：{item.title}", "提取主要内容、AI 前沿关联、待核验信息。", [item])

    def build_research_pack(self, topic: Topic) -> IntelligenceResult:
        return self._generate(f"资料包：{topic.title}", "整理资料脉络、核心事实、可继续追问的问题。", _topic_items(topic))

    def analyze_evidence(self, topic: Topic) -> IntelligenceResult:
        return self._generate(f"证据分析：{topic.title}", "输出可确认事实、谨慎推断、未知与风险、下一步核验建议。", _topic_items(topic))

    def summarize_topic(self, sources: list[SourceItem]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": _topic_summary_instructions()},
                {"role": "user", "content": "请综合以下近七天来源，写热点摘要：\n\n" + _topic_summary_context(sources)},
            ],
        )
        return (response.choices[0].message.content or "").strip()


def validate_openai_model_access(settings: Settings) -> None:
    """Verify the configured model is available before the web service starts."""
    if not settings.openai_api_key:
        return

    try:
        provider = OpenAIIntelligence(settings.openai_api_key, settings.openai_model)
        provider.client.models.retrieve(settings.openai_model)
    except Exception as error:
        raise OpenAIModelValidationError(
            f"无法使用 OPENAI_MODEL={settings.openai_model!r}。请确认该模型名称正确，"
            "并且当前 OPENAI_API_KEY 对应的 API 项目已获得该模型访问权限；"
            "如无权限，可在 .env 中改用该项目可用的模型（例如 gpt-5.5）。"
        ) from error


def validate_selected_provider_access(settings: Settings) -> None:
    if settings.ai_provider.strip().casefold() == "openai":
        validate_openai_model_access(settings)


def get_intelligence_provider(settings: Settings) -> IntelligenceProvider:
    provider = settings.ai_provider.strip().casefold()
    if provider == "deepseek" and settings.deepseek_api_key:
        return DeepSeekIntelligence(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_base_url)
    if provider == "openai" and settings.openai_api_key:
        return OpenAIIntelligence(settings.openai_api_key, settings.openai_model)
    if provider == "auto" and settings.openai_api_key:
        return OpenAIIntelligence(settings.openai_api_key, settings.openai_model)
    if provider == "auto" and settings.deepseek_api_key:
        return DeepSeekIntelligence(settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_base_url)
    return LocalEvidenceIntelligence()
