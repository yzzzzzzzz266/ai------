from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Draft, SourceItem, Topic, TopicEvidence


def seed_demo_data(session: Session) -> None:
    if session.scalar(select(func.count(SourceItem.id))) > 0:
        return

    now = datetime.now(timezone.utc)
    sources = [
        SourceItem(
            platform="arXiv",
            external_id="demo-arxiv-1",
            title="多模态推理模型的评测方法更新",
            content="一篇近期论文讨论了多模态推理任务中的评测设置与可复现性问题。",
            url="https://arxiv.org/",
            author="AI Radar 演示来源",
            published_at=now - timedelta(hours=2),
            fetched_at=now,
            metrics_json={"citations": 0},
            language="zh",
            raw_json={"demo": True},
        ),
        SourceItem(
            platform="GitHub",
            external_id="demo-github-1",
            title="开源 Agent 工作流工具获得开发者关注",
            content="该项目为工具调用、任务分解和运行轨迹提供了可观察的基础能力。",
            url="https://github.com/",
            author="AI Radar 演示来源",
            published_at=now - timedelta(hours=5),
            fetched_at=now,
            metrics_json={"stars": 128},
            language="zh",
            raw_json={"demo": True},
        ),
        SourceItem(
            platform="Hacker News",
            external_id="demo-hn-1",
            title="开发者讨论 LLM Agent 的可靠性边界",
            content="讨论聚焦长任务执行中工具调用失败、验证机制与人工介入的取舍。",
            url="https://news.ycombinator.com/",
            author="AI Radar 演示来源",
            published_at=now - timedelta(hours=9),
            fetched_at=now,
            metrics_json={"points": 86},
            language="zh",
            raw_json={"demo": True},
        ),
    ]
    session.add_all(sources)
    session.flush()

    topic = Topic(
        title="AI Agent 从能力演示走向可靠性验证",
        summary="多模态评测、开源工作流工具与开发者讨论共同指向 Agent 的可靠性和可观察性问题。",
        heat_score=87.5,
        freshness="近 24 小时",
        latest_published_at=now - timedelta(hours=2),
        status="active",
    )
    session.add(topic)
    session.flush()
    session.add_all(
        [
            TopicEvidence(topic_id=topic.id, source_item_id=source.id, relevance_score=0.91)
            for source in sources
        ]
    )
    session.add(
        Draft(
            topic_id=topic.id,
            mode="新闻快讯",
            title="AI Agent 的下一步：从能力演示转向可靠性验证",
            content_markdown="现有信息显示，近期围绕 AI Agent 的讨论开始更关注任务执行的稳定性、工具调用的可观察性和评测方法。",
            image_prompt="中文科技新闻插画，抽象智能体协作流程，深蓝与暖橙配色，无文字，横向构图",
            editor_params_json={"audience": "AI 从业者", "tone": "新闻"},
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()

