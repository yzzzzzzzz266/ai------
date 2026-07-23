# AI Radar

AI Radar 是一个面向 AI 内容创作者的本地 MVP，用于汇总热点信息、建立可追溯的话题证据，并在后续阶段生成文章草稿与配图提示词。

## 阶段一已实现

- FastAPI + Jinja2 应用骨架与中文首页；
- SQLite + SQLAlchemy 数据模型；
- 可重复加载的演示来源、话题、证据和草稿；
- 基于 `.env` 的配置；
- 健康检查接口：`/health`；
- 热点话题筛选、话题详情、草稿编辑保存和 Markdown 导出。
- arXiv、GitHub、Hacker News 与可配置 RSS 的公开信息采集；
- 手动采集、APScheduler 定时采集、来源状态和错误隔离。

## 环境要求

- Python 3.11 或更高版本；
- 推荐使用 [uv](https://docs.astral.sh/uv/) 管理依赖。

## 安装与启动

在 `项目本体` 目录执行：

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run uvicorn app.main:app --reload
```

首次运行时，uv 会创建虚拟环境并安装依赖。随后打开 `http://127.0.0.1:8000`。

如需自定义配置，先复制 `.env.example` 为 `.env`，再修改其中的值。未配置任何外部 API Key 时，`DEMO_MODE=true` 仍会加载完整的演示数据。

`RSS_URLS` 可配置一个或多个以逗号或换行分隔的公开 RSS 地址。GitHub Token 是可选项，用于提高 GitHub API 的请求额度。应用不会绕过登录、验证码或平台访问控制；某一来源不可用时，状态面板会显示错误，但其他来源继续运行。

## 测试

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
uv run pytest
```

## 当前边界

真实采集只保存来源链接和短摘要。当前的热点聚合仍以演示数据为主；更完整的话题自动聚合和文章生成将在后续阶段逐步实现。
