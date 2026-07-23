from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models import SourceItem, Topic


WRITING_MODES = ("新闻快讯", "编辑解读", "创作者选题", "技术拆解")


@dataclass(frozen=True)
class EditorParameters:
    audience: str
    writing_style: str
    stance: str
    target_length: str
    banned_words: str
    required_facts: str
    avoided_angles: str

    def as_dict(self) -> dict[str, str]:
        return {
            "audience": self.audience,
            "writing_style": self.writing_style,
            "stance": self.stance,
            "target_length": self.target_length,
            "banned_words": self.banned_words,
            "required_facts": self.required_facts,
            "avoided_angles": self.avoided_angles,
        }


@dataclass(frozen=True)
class GeneratedDraft:
    title: str
    content_markdown: str
    image_prompt: str
    provider_name: str


class DraftGenerator(Protocol):
    name: str

    def generate(self, topic: Topic, parameters: EditorParameters, mode: str) -> GeneratedDraft: ...


def _source_label(item: SourceItem) -> str:
    date_label = item.published_at.strftime("%Y-%m-%d")
    return f"[{item.platform}：{item.title}]({item.url})（{item.author or '来源未提供作者'}，{date_label}）"


def _evidence(topic: Topic) -> list[SourceItem]:
    evidences = sorted(topic.evidences, key=lambda evidence: evidence.source_item.published_at, reverse=True)
    return [evidence.source_item for evidence in evidences]


def _source_section(items: list[SourceItem]) -> str:
    if not items:
        return "## 可追溯来源\n\n- 现有信息不足以确认，暂无可引用来源。"
    return "## 可追溯来源\n\n" + "\n".join(f"- {_source_label(item)}" for item in items)


class EvidenceTemplateGenerator:
    name = "evidence-template"

    def generate(self, topic: Topic, parameters: EditorParameters, mode: str) -> GeneratedDraft:
        items = _evidence(topic)
        if not items:
            body = "现有信息不足以确认该话题的具体进展，因此不补写来源之外的细节。"
            return GeneratedDraft(topic.title, f"{body}\n\n{_source_section(items)}", self._image_prompt(topic), self.name)

        lead = _source_label(items[0])
        secondary = _source_label(items[1]) if len(items) > 1 else None
        details = "；".join(item.title for item in items[:3])
        position = {
            "只陈述事实": "下文只陈述来源可确认的信息，不延伸为结论。",
            "谨慎分析": "以下分析仅基于来源间的共同信号，仍需后续资料验证。",
            "明确观点": "以下观点建立在已列来源之上，不将推断写成既成事实。",
        }.get(parameters.stance, "下文以来源可确认的信息为边界。")
        audience_note = f"面向{parameters.audience}，采用{parameters.writing_style}表达。"

        if mode == "新闻快讯":
            body = (
                f"{topic.title}出现了可追溯的新信号。{lead}指出“{items[0].title}”。"
                f"{f'另一条来源 {secondary} 提供了补充。' if secondary else ''}\n\n"
                f"现有证据涉及：{details}。{position} {audience_note}"
            )
        elif mode == "编辑解读":
            body = (
                f"{topic.title}的核心不是单一产品或论文，而是多条来源同时指向的变化。{lead}是当前最接近该变化的证据。"
                f"{f'与此同时，{secondary} 从另一侧补充了这一信号。' if secondary else ''}\n\n"
                f"可以谨慎得出的判断是：{details} 正在把讨论推向同一方向。{position}\n\n"
                "反面限制也需要保留：这些来源的指标、样本范围和发布时间并不完全一致，不能据此确认行业整体趋势。"
            )
        elif mode == "创作者选题":
            body = (
                f"可将“{topic.title}”做成面向{parameters.audience}的内容选题。起点应是 {lead}，不要把它扩写成来源没有提供的行业结论。\n\n"
                f"建议角度：用“{details}”解释为什么创作者需要关注这个信号；争议点是这些线索是否已经足以证明长期变化。{position}\n\n"
                "可制作的内容包括：一张来源时间线、一次证据对照，以及一段明确标注未知部分的结尾。"
            )
        else:
            body = (
                f"拆解“{topic.title}”时，应先从可复核证据开始：{lead}。"
                f"{f'补充材料见 {secondary}。' if secondary else ''}\n\n"
                f"目前可确认的线索包括：{details}。这些材料分别涉及方法、工具、评测或开发者讨论，但没有形成统一实验条件。\n\n"
                f"复现与评估时，应记录来源中的模型、仓库或论文名称，并核对其公开指标、限制和更新时间。{position}"
            )

        required_matches = [
            value.strip()
            for value in parameters.required_facts.replace("，", ",").split(",")
            if value.strip() and any(value.strip().casefold() in f"{item.title} {item.content} {item.url}".casefold() for item in items)
        ]
        if required_matches:
            body += "\n\n编辑要求中已由来源确认的要点：" + "、".join(required_matches) + "。"
        if parameters.avoided_angles.strip():
            body += "\n\n已避免的角度：" + parameters.avoided_angles.strip() + "。"

        content = f"{body}\n\n{_source_section(items)}"
        return GeneratedDraft(topic.title, content, self._image_prompt(topic), self.name)

    def _image_prompt(self, topic: Topic) -> str:
        return f"中文 AI 科技资讯插画，主题为“{topic.title}”，抽象数据流与协作界面，专业克制，深蓝和暖橙配色，无文字，无品牌标识，横向构图"


def get_draft_generator() -> DraftGenerator:
    return EvidenceTemplateGenerator()
