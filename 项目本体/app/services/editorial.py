from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


REWRITE_MODES = ("更具体", "更克制", "更像新闻编辑", "更像技术作者")
SOURCE_LINK_PATTERN = re.compile(r"\[[^\]]+\]\([^\)]+\)")
GENERIC_PHRASES = ("值得注意的是", "随着", "这个快速变化的时代", "未来可期", "总而言之", "不难发现")
STRONG_CONCLUSION_WORDS = ("首次", "领先", "爆发", "颠覆", "重大", "必然", "唯一", "革命性")
CONNECTORS = ("首先", "其次", "最后", "此外", "同时", "因此", "不过", "值得注意的是")


@dataclass(frozen=True)
class EditorialReview:
    factual_statement_count: int
    sourced_paragraph_ratio: int
    unsupported_judgments: list[str]
    repeated_connectors: list[str]
    generic_sentences: list[str]
    strong_conclusions: list[str]


def _sentences(content: str) -> list[str]:
    return [sentence.strip() for sentence in re.split(r"(?<=[。！？.!?])\s*", content) if sentence.strip()]


def _paragraphs(content: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", content) if paragraph.strip()]


def review_content(content: str) -> EditorialReview:
    paragraphs = _paragraphs(content)
    narrative_paragraphs = [paragraph for paragraph in paragraphs if not paragraph.startswith("## 可追溯来源")]
    sourced_paragraphs = sum(bool(SOURCE_LINK_PATTERN.search(paragraph)) for paragraph in narrative_paragraphs)
    ratio = round(sourced_paragraphs / len(narrative_paragraphs) * 100) if narrative_paragraphs else 0
    sentences = _sentences(content)
    factual_statement_count = sum(
        bool(re.search(r"\d|来源|发布|显示|指出|根据|模型|论文|仓库|API", sentence))
        for sentence in sentences
    )
    unsupported_judgments = [
        sentence
        for sentence in sentences
        if any(word in sentence for word in STRONG_CONCLUSION_WORDS)
        and not SOURCE_LINK_PATTERN.search(sentence)
    ][:5]
    connector_counts = Counter(
        connector
        for connector in CONNECTORS
        for sentence in sentences
        if connector in sentence
    )
    repeated_connectors = [f"{connector}（{count} 次）" for connector, count in connector_counts.items() if count > 1]
    generic_sentences = [
        sentence
        for sentence in sentences
        if any(phrase in sentence for phrase in GENERIC_PHRASES)
    ][:5]
    strong_conclusions = [
        sentence
        for sentence in sentences
        if any(word in sentence for word in STRONG_CONCLUSION_WORDS)
    ][:5]
    return EditorialReview(
        factual_statement_count=factual_statement_count,
        sourced_paragraph_ratio=ratio,
        unsupported_judgments=unsupported_judgments,
        repeated_connectors=repeated_connectors,
        generic_sentences=generic_sentences,
        strong_conclusions=strong_conclusions,
    )


def rewrite_content(content: str, mode: str) -> str:
    if mode not in REWRITE_MODES:
        raise ValueError("不支持的改写模式")

    source_links = SOURCE_LINK_PATTERN.findall(content)
    replacements = {
        "更具体": {
            "值得注意的是，": "",
            "值得注意的是": "",
            "这一趋势": "这一变化",
            "相关方面": "已列来源",
        },
        "更克制": {
            "颠覆": "可能改变",
            "爆发": "快速增加",
            "领先": "处于前列",
            "重大": "值得关注",
            "革命性": "显著",
            "必然": "可能",
        },
        "更像新闻编辑": {
            "我们认为": "来源显示",
            "显然": "目前资料显示",
            "可以看到": "来源显示",
            "不难发现": "已有来源表明",
        },
        "更像技术作者": {
            "能力": "实现与评测线索",
            "讨论": "技术讨论",
            "变化": "实现变化",
        },
    }
    rewritten = content
    for source, target in replacements[mode].items():
        rewritten = rewritten.replace(source, target)
    if SOURCE_LINK_PATTERN.findall(rewritten) != source_links:
        return content
    return rewritten
