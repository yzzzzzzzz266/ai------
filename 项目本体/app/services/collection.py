from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import CollectionRun, SourceItem


AI_KEYWORDS = (
    "ai",
    "artificial intelligence",
    "llm",
    "large language model",
    "agent",
    "reasoning",
    "multimodal",
    "machine learning",
    "deep learning",
    "generative",
    "人工智能",
    "大模型",
    "智能体",
    "多模态",
    "开源模型",
)
FRONTIER_SIGNAL_KEYWORDS = (
    "model release",
    "release",
    "benchmark",
    "reasoning",
    "agent",
    "multimodal",
    "open source",
    "api",
    "paper",
    "arxiv",
    "inference",
    "training",
    "模型发布",
    "评测",
    "推理",
    "智能体",
    "多模态",
    "开源",
    "论文",
    "接口",
)
REQUEST_TIMEOUT_SECONDS = 15.0
USER_AGENT = "AI-Radar-MVP/0.2"


@dataclass(frozen=True)
class SourceItemPayload:
    platform: str
    external_id: str | None
    title: str
    content: str
    url: str
    author: str | None
    published_at: datetime
    metrics_json: dict[str, Any]
    language: str
    raw_json: dict[str, Any]


@dataclass(frozen=True)
class PersistStats:
    added_count: int = 0
    duplicate_count: int = 0
    filtered_count: int = 0


class SourceAdapter(Protocol):
    name: str

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]: ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return utc_now()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_unix_timestamp(value: Any) -> datetime:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return utc_now()


def configured_values(value: str) -> list[str]:
    return [entry.strip().lstrip("@") for entry in re.split(r"[\n,]", value) if entry.strip()]


def strip_markup(value: str) -> str:
    normalized = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", normalized).strip()


def detect_language(value: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", value) else "en"


def is_ai_related(item: SourceItemPayload) -> bool:
    searchable = f"{item.title} {item.content}".casefold()
    return any(keyword in searchable for keyword in AI_KEYWORDS) and any(
        keyword in searchable for keyword in FRONTIER_SIGNAL_KEYWORDS
    )


def normalized_external_id(item: SourceItemPayload) -> str:
    if item.external_id:
        return item.external_id[:255]
    return hashlib.sha256(item.url.encode("utf-8")).hexdigest()


def persist_items(session: Session, items: list[SourceItemPayload]) -> PersistStats:
    added_count = duplicate_count = filtered_count = 0
    fetched_at = utc_now()

    for item in items:
        if not item.title or not item.url or not is_ai_related(item):
            filtered_count += 1
            continue

        external_id = normalized_external_id(item)
        existing = session.scalar(
            select(SourceItem).where(
                SourceItem.platform == item.platform,
                SourceItem.external_id == external_id,
            )
        )
        if existing is None:
            existing = session.scalar(select(SourceItem).where(SourceItem.url == item.url))
        if existing is not None:
            duplicate_count += 1
            continue

        session.add(
            SourceItem(
                platform=item.platform,
                external_id=external_id,
                title=item.title[:500],
                content=item.content,
                url=item.url[:1000],
                author=item.author[:255] if item.author else None,
                published_at=item.published_at,
                fetched_at=fetched_at,
                metrics_json=item.metrics_json,
                language=item.language,
                raw_json=item.raw_json,
            )
        )
        added_count += 1

    session.commit()
    return PersistStats(added_count, duplicate_count, filtered_count)


class ArxivAdapter:
    name = "arXiv"

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        response = client.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": "cat:cs.AI OR cat:cs.CL OR cat:cs.LG",
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": 15,
            },
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        namespace = {"atom": "http://www.w3.org/2005/Atom"}
        items: list[SourceItemPayload] = []
        for entry in root.findall("atom:entry", namespace):
            url = (entry.findtext("atom:id", default="", namespaces=namespace) or "").strip()
            title = strip_markup(entry.findtext("atom:title", default="", namespaces=namespace))
            content = strip_markup(entry.findtext("atom:summary", default="", namespaces=namespace))
            authors = [
                author.findtext("atom:name", default="", namespaces=namespace)
                for author in entry.findall("atom:author", namespace)
            ]
            published = entry.findtext("atom:published", default="", namespaces=namespace)
            items.append(
                SourceItemPayload(
                    platform=self.name,
                    external_id=url.rsplit("/", 1)[-1] or None,
                    title=title,
                    content=content,
                    url=url,
                    author=", ".join(author for author in authors if author) or None,
                    published_at=parse_datetime(published),
                    metrics_json={},
                    language=detect_language(f"{title} {content}"),
                    raw_json={"source": "arxiv"},
                )
            )
        return items


class GitHubAdapter:
    name = "GitHub"

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        since = (utc_now() - timedelta(days=30)).date().isoformat()
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = client.get(
            "https://api.github.com/search/repositories",
            params={"q": f"topic:artificial-intelligence created:>={since}", "sort": "updated", "order": "desc", "per_page": 15},
            headers=headers,
        )
        response.raise_for_status()
        items: list[SourceItemPayload] = []
        for repository in response.json().get("items", []):
            title = repository.get("full_name", "")
            description = repository.get("description") or ""
            items.append(
                SourceItemPayload(
                    platform=self.name,
                    external_id=str(repository.get("node_id") or repository.get("id") or "") or None,
                    title=title,
                    content=description,
                    url=repository.get("html_url", ""),
                    author=(repository.get("owner") or {}).get("login"),
                    published_at=parse_datetime(repository.get("created_at")),
                    metrics_json={"stars": repository.get("stargazers_count", 0), "forks": repository.get("forks_count", 0)},
                    language=detect_language(f"{title} {description}"),
                    raw_json={"topics": repository.get("topics", []), "updated_at": repository.get("updated_at")},
                )
            )
        return items


class HackerNewsAdapter:
    name = "Hacker News"

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        response = client.get(
            "https://hn.algolia.com/api/v1/search_by_date",
            params={"query": "AI LLM agent multimodal", "tags": "story", "hitsPerPage": 20},
        )
        response.raise_for_status()
        items: list[SourceItemPayload] = []
        for hit in response.json().get("hits", []):
            title = hit.get("title") or hit.get("story_title") or ""
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
            content = hit.get("story_text") or ""
            items.append(
                SourceItemPayload(
                    platform=self.name,
                    external_id=hit.get("objectID"),
                    title=title,
                    content=strip_markup(content),
                    url=url,
                    author=hit.get("author"),
                    published_at=parse_datetime(hit.get("created_at")),
                    metrics_json={"points": hit.get("points", 0), "comments": hit.get("num_comments", 0)},
                    language=detect_language(f"{title} {content}"),
                    raw_json={"object_id": hit.get("objectID")},
                )
            )
        return items


class RssAdapter:
    name = "RSS"

    def __init__(self, feed_urls: list[str]) -> None:
        self.feed_urls = feed_urls

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        items: list[SourceItemPayload] = []
        for feed_url in self.feed_urls:
            response = client.get(feed_url)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            for entry in root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry"):
                items.append(self._payload_from_entry(entry, feed_url))
        return [item for item in items if item is not None]

    def _payload_from_entry(self, entry: ElementTree.Element, feed_url: str) -> SourceItemPayload | None:
        atom = "{http://www.w3.org/2005/Atom}"
        title = strip_markup(entry.findtext("title") or entry.findtext(f"{atom}title") or "")
        link_element = entry.find("link")
        if link_element is None:
            link_element = entry.find(f"{atom}link")
        url = ""
        if link_element is not None:
            url = link_element.get("href") or (link_element.text or "")
        url = url or entry.findtext("guid") or feed_url
        content = strip_markup(
            entry.findtext("description")
            or entry.findtext(f"{atom}summary")
            or entry.findtext(f"{atom}content")
            or ""
        )
        author = entry.findtext("author") or entry.findtext(f"{atom}author/{atom}name")
        published = entry.findtext("pubDate") or entry.findtext(f"{atom}published") or entry.findtext(f"{atom}updated")
        if not title:
            return None
        return SourceItemPayload(
            platform=self.name,
            external_id=entry.findtext("guid") or url,
            title=title,
            content=content,
            url=url,
            author=author,
            published_at=parse_datetime(published),
            metrics_json={"feed_url": feed_url},
            language=detect_language(f"{title} {content}"),
            raw_json={"feed_url": feed_url},
        )


class XAdapter:
    name = "X"

    def __init__(self, bearer_token: str, usernames: list[str]) -> None:
        self.bearer_token = bearer_token
        self.usernames = usernames

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        users_response = client.get(
            "https://api.x.com/2/users/by",
            params={"usernames": ",".join(self.usernames), "user.fields": "username,name"},
            headers=headers,
        )
        users_response.raise_for_status()
        items: list[SourceItemPayload] = []
        for user in users_response.json().get("data", []):
            user_id = user.get("id")
            username = user.get("username")
            if not user_id or not username:
                continue
            tweets_response = client.get(
                f"https://api.x.com/2/users/{user_id}/tweets",
                params={
                    "max_results": 10,
                    "exclude": "replies,retweets",
                    "tweet.fields": "created_at,public_metrics",
                },
                headers=headers,
            )
            tweets_response.raise_for_status()
            for tweet in tweets_response.json().get("data", []):
                text = (tweet.get("text") or "").strip()
                tweet_id = str(tweet.get("id") or "")
                if not text or not tweet_id:
                    continue
                items.append(
                    SourceItemPayload(
                        platform=self.name,
                        external_id=tweet_id,
                        title=text[:180],
                        content=text,
                        url=f"https://x.com/{username}/status/{tweet_id}",
                        author=username,
                        published_at=parse_datetime(tweet.get("created_at")),
                        metrics_json=tweet.get("public_metrics") or {},
                        language=detect_language(text),
                        raw_json={"user_id": user_id, "username": username, "source": "x-api"},
                    )
                )
        return items


class BilibiliAdapter:
    name = "Bilibili"

    def __init__(self, author_mids: list[str]) -> None:
        self.author_mids = author_mids

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        items: list[SourceItemPayload] = []
        for mid in self.author_mids:
            response = client.get(f"https://space.bilibili.com/{mid}/video")
            response.raise_for_status()
            match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.+?})\s*;\s*</script>", response.text, re.DOTALL)
            if not match:
                raise RuntimeError(f"Bilibili public page did not expose video data for MID {mid}")
            state = json.loads(match.group(1))
            author = str((state.get("card") or {}).get("name") or mid)
            seen_bvids: set[str] = set()
            for video in self._video_records(state):
                bvid = str(video.get("bvid") or "")
                title = strip_markup(str(video.get("title") or ""))
                if not bvid or not title or bvid in seen_bvids:
                    continue
                seen_bvids.add(bvid)
                description = strip_markup(str(video.get("description") or ""))
                stat = video.get("stat") or {}
                items.append(
                    SourceItemPayload(
                        platform=self.name,
                        external_id=bvid,
                        title=title,
                        content=description,
                        url=f"https://www.bilibili.com/video/{bvid}",
                        author=author,
                        published_at=parse_unix_timestamp(video.get("created") or video.get("pubdate")),
                        metrics_json={
                            "views": stat.get("view", video.get("play", 0)),
                            "likes": stat.get("like", 0),
                            "comments": stat.get("reply", video.get("video_review", 0)),
                        },
                        language=detect_language(f"{title} {description}"),
                        raw_json={"mid": mid, "bvid": bvid, "source": "bilibili-public-space"},
                    )
                )
        return items

    def _video_records(self, value: Any):
        if isinstance(value, dict):
            if value.get("bvid") and value.get("title"):
                yield value
            for child in value.values():
                yield from self._video_records(child)
        elif isinstance(value, list):
            for child in value:
                yield from self._video_records(child)


def build_adapters(settings: Settings) -> list[SourceAdapter]:
    feed_urls = configured_values(settings.rss_urls)
    adapters: list[SourceAdapter] = [ArxivAdapter(), GitHubAdapter(settings.github_token), HackerNewsAdapter()]
    if feed_urls:
        adapters.append(RssAdapter(feed_urls))
    x_usernames = configured_values(settings.x_author_usernames)
    if settings.x_bearer_token and x_usernames:
        adapters.append(XAdapter(settings.x_bearer_token, x_usernames))
    bilibili_mids = configured_values(settings.bilibili_author_mids)
    if bilibili_mids:
        adapters.append(BilibiliAdapter(bilibili_mids))
    return adapters


def collect_sources(session_factory: sessionmaker[Session], settings: Settings) -> None:
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for adapter in build_adapters(settings):
            with session_factory() as session:
                run = CollectionRun(source_name=adapter.name, status="running", started_at=utc_now())
                session.add(run)
                session.commit()
                try:
                    stats = persist_items(session, adapter.fetch(client))
                    run.status = "success"
                    run.added_count = stats.added_count
                    run.duplicate_count = stats.duplicate_count
                    run.filtered_count = stats.filtered_count
                except Exception as error:
                    session.rollback()
                    run = session.get(CollectionRun, run.id)
                    run.status = "failed"
                    run.error_message = str(error)[:1000]
                run.finished_at = utc_now()
                session.commit()


def latest_collection_runs(session: Session) -> list[CollectionRun]:
    latest_by_source: dict[str, CollectionRun] = {}
    runs = session.scalars(select(CollectionRun).order_by(CollectionRun.started_at.desc())).all()
    for run in runs:
        latest_by_source.setdefault(run.source_name, run)
    return list(latest_by_source.values())
