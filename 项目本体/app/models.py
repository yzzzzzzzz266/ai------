from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_source_item_platform_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(80), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(1000), unique=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    language: Mapped[str] = mapped_column(String(32), default="en")
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    topic_evidences: Mapped[list[TopicEvidence]] = relationship(back_populates="source_item")


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300), unique=True)
    summary: Mapped[str] = mapped_column(Text)
    heat_score: Mapped[float] = mapped_column(Float, default=0)
    freshness: Mapped[str] = mapped_column(String(50), default="new")
    latest_published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")

    evidences: Mapped[list[TopicEvidence]] = relationship(back_populates="topic", cascade="all, delete-orphan")
    drafts: Mapped[list[Draft]] = relationship(back_populates="topic", cascade="all, delete-orphan")


class TopicEvidence(Base):
    __tablename__ = "topic_evidences"
    __table_args__ = (UniqueConstraint("topic_id", "source_item_id", name="uq_topic_source_item"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    source_item_id: Mapped[int] = mapped_column(ForeignKey("source_items.id"), index=True)
    relevance_score: Mapped[float] = mapped_column(Float, default=1)

    topic: Mapped[Topic] = relationship(back_populates="evidences")
    source_item: Mapped[SourceItem] = relationship(back_populates="topic_evidences")


class Draft(Base):
    __tablename__ = "drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    mode: Mapped[str] = mapped_column(String(50), default="新闻快讯")
    title: Mapped[str] = mapped_column(String(500))
    content_markdown: Mapped[str] = mapped_column(Text)
    image_prompt: Mapped[str] = mapped_column(Text, default="")
    editor_params_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    topic: Mapped[Topic] = relationship(back_populates="drafts")


class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    filtered_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
