# Chinese Tech Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect AI-relevant posts from IT Home and Juejin as distinct, failure-isolated sources.

**Architecture:** IT Home uses its public RSS feed, parsed by the existing RSS parser with a source-specific platform label. Juejin uses its public recommendation API and converts records into the existing `SourceItemPayload` contract. Both adapters are enabled by their endpoint settings and are registered separately by `build_adapters`.

**Tech Stack:** Python 3.12, httpx, Pydantic Settings, ElementTree, pytest.

---

## File Structure

- Modify: `app/config.py` to expose the IT Home RSS and Juejin public API endpoints.
- Modify: `app/services/collection.py` to add the two adapters and register them independently.
- Modify: `tests/test_collection.py` to specify parser output and adapter registration.
- Modify: `.env.example` and `官方RSS源清单.md` to document the public endpoints.

### Task 1: Specify the adapter behavior

**Files:**
- Modify: `tests/test_collection.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_ithome_adapter_labels_rss_items_with_its_platform() -> None:
    xml = b"""<rss><channel><item><guid>123</guid><title>AI agent update</title><link>https://www.ithome.com/0/1/123.htm</link><description>AI model release</description><pubDate>Sat, 01 Aug 2026 10:00:00 +0000</pubDate></item></channel></rss>"""
    response = httpx.Response(200, content=xml, request=httpx.Request("GET", "https://www.ithome.com/rss/"))

    class FakeClient:
        def get(self, _url: str):
            return response

    items = IthomeAdapter("https://www.ithome.com/rss/").fetch(FakeClient())

    assert [(item.platform, item.external_id) for item in items] == [("IT之家", "123")]


def test_juejin_adapter_maps_public_recommendation_records() -> None:
    response = httpx.Response(200, json={"data": [{"item_info": {"article_id": "article-1", "article_info": {"title": "AI agent workflow", "brief_content": "AI model release details", "ctime": "1785578400"}, "author_user_info": {"user_name": "juejin-author"}, "article_info": {"article_id": "article-1", "title": "AI agent workflow", "brief_content": "AI model release details", "ctime": "1785578400", "digg_count": 4, "comment_count": 2}}}]}, request=httpx.Request("POST", "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"))

    class FakeClient:
        def post(self, _url: str, json: dict[str, int]):
            assert json == {"id_type": 2, "sort_type": 200, "cursor": "0", "limit": 20}
            return response

    items = JuejinAdapter("https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed").fetch(FakeClient())

    assert [(item.platform, item.external_id, item.url) for item in items] == [
        ("稀土掘金", "article-1", "https://juejin.cn/post/article-1")
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collection.py -k "ithome or juejin" -v`

Expected: FAIL during collection-module import because `IthomeAdapter` and `JuejinAdapter` do not exist.

### Task 2: Implement the adapters and registration

**Files:**
- Modify: `app/config.py`
- Modify: `app/services/collection.py`

- [ ] **Step 1: Add configurable defaults**

```python
ithome_rss_url: str = "https://www.ithome.com/rss/"
juejin_api_url: str = "https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed"
```

- [ ] **Step 2: Add the minimal adapter implementations**

```python
class IthomeAdapter(RssAdapter):
    name = "IT之家"

    def __init__(self, feed_url: str) -> None:
        super().__init__([feed_url])

    def _payload_from_entry(self, entry: ElementTree.Element, feed_url: str) -> SourceItemPayload | None:
        payload = super()._payload_from_entry(entry, feed_url)
        return SourceItemPayload(**{**payload.__dict__, "platform": self.name}) if payload else None


class JuejinAdapter:
    name = "稀土掘金"

    def __init__(self, api_url: str) -> None:
        self.api_url = api_url

    def fetch(self, client: httpx.Client) -> list[SourceItemPayload]:
        response = client.post(self.api_url, json={"id_type": 2, "sort_type": 200, "cursor": "0", "limit": 20})
        response.raise_for_status()
        items: list[SourceItemPayload] = []
        for record in response.json().get("data", []):
            item = record.get("item_info") or {}
            article = item.get("article_info") or {}
            article_id = str(article.get("article_id") or item.get("article_id") or "")
            title = str(article.get("title") or "")
            if not article_id or not title:
                continue
            content = strip_markup(str(article.get("brief_content") or ""))
            items.append(SourceItemPayload(
                platform=self.name, external_id=article_id, title=title, content=content,
                url=f"https://juejin.cn/post/{article_id}",
                author=(item.get("author_user_info") or {}).get("user_name"),
                published_at=parse_unix_timestamp(article.get("ctime")),
                metrics_json={"likes": article.get("digg_count", 0), "comments": article.get("comment_count", 0)},
                language=detect_language(f"{title} {content}"),
                raw_json={"article_id": article_id, "source": "juejin-public-api"},
            ))
        return items
```

- [ ] **Step 3: Register enabled endpoints separately**

```python
if settings.ithome_rss_url:
    adapters.append(IthomeAdapter(settings.ithome_rss_url))
if settings.juejin_api_url:
    adapters.append(JuejinAdapter(settings.juejin_api_url))
```

- [ ] **Step 4: Run focused tests to verify they pass**

Run: `uv run pytest tests/test_collection.py -k "ithome or juejin" -v`

Expected: PASS with 2 selected tests.

### Task 3: Document endpoints and verify the suite

**Files:**
- Modify: `.env.example`
- Modify: `官方RSS源清单.md`

- [ ] **Step 1: Document the enabled endpoint settings**

```dotenv
ITHOME_RSS_URL=https://www.ithome.com/rss/
JUEJIN_API_URL=https://api.juejin.cn/recommend_api/v1/article/recommend_all_feed
```

- [ ] **Step 2: Run the collection test module**

Run: `uv run pytest tests/test_collection.py -v`

Expected: PASS with no failures.

- [ ] **Step 3: Run the full test suite**

Run: `uv run pytest -q`

Expected: PASS with no failures.

- [ ] **Step 4: Commit the implementation**

```bash
git add 项目本体/app/config.py 项目本体/app/services/collection.py 项目本体/tests/test_collection.py 项目本体/.env.example 项目本体/官方RSS源清单.md
git commit -m "feat: add Chinese tech news sources"
```
