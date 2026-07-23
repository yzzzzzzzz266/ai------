# AI Radar

AI Radar 是面向 AI 内容创作者的本地 MVP：它从公开来源采集 AI 信号，按可解释规则聚合热点话题，保留来源证据，并生成和编辑可追溯的 Markdown 草稿。

## 已实现能力

- FastAPI、Jinja2、HTMX、Tailwind CSS 中文界面；
- SQLite + SQLAlchemy 数据模型与演示模式；
- 仪表盘、关键词筛选、话题详情、来源证据和 Markdown 导出；
- arXiv、GitHub、Hacker News 与可配置 RSS 公开采集；
- 单源超时/异常隔离、去重、AI 相关性过滤、手动采集和 APScheduler 定时采集；
- 基于关键词规则的话题聚合、热度/新鲜度计算和证据关联；
- 新闻快讯、编辑解读、创作者选题、技术拆解四种草稿模式；
- 无 API Key 也可使用的本地证据模板生成器；
- 编辑检查面板与“更具体 / 更克制 / 更像新闻编辑 / 更像技术作者”安全改写。

## 架构

```text
app/
├── main.py                 # FastAPI 路由、页面和后台入口
├── models.py               # SourceItem、Topic、TopicEvidence、Draft、CollectionRun
├── services/
│   ├── collection.py       # 公开源适配、过滤、去重、运行状态
│   ├── topics.py           # 可解释话题聚合
│   ├── drafts.py           # 证据模板草稿生成器
│   └── editorial.py        # 编辑检查与安全改写
├── templates/              # Jinja2 页面与 HTMX 局部模板
└── static/                 # 样式
```

## 环境要求

- Python 3.11 或更高版本；
- 推荐使用 `uv` 管理 Python 环境和依赖。

## 安装与启动

在 `项目本体` 目录执行：

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.uv-python"
uv run uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000`。首次启动会创建 SQLite 表并在 `DEMO_MODE=true` 时写入演示数据。

## 配置

复制 `.env.example` 为 `.env` 后按需调整：

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | SQLite 数据库地址 |
| `DEMO_MODE` | 没有外部配置时仍加载完整演示闭环 |
| `RSS_URLS` | 逗号或换行分隔的公开 RSS 地址 |
| `GITHUB_TOKEN` | 可选；提高 GitHub API 请求额度 |
| `COLLECTION_INTERVAL_MINUTES` | 定时采集间隔，最小 1 分钟 |
| `SCHEDULER_ENABLED` | 是否启动 APScheduler |
| `DRAFT_GENERATOR_PROVIDER` | 当前为 `template`，不需要模型 API Key |
| `X_BEARER_TOKEN`、`COMFYUI_URL` | 为后续可选能力预留，当前不启用 |

## 使用流程

1. 在首页点击“立即采集”，查看各公开来源的独立运行状态；
2. 点击“生成热点”，将已入库来源按规则聚合为话题；
3. 打开话题详情，核对来源、作者、时间和原始链接；
4. 点击“生成证据草稿”，选择模式与编辑参数；
5. 在草稿页修改 Markdown、配图提示词和参数，查看编辑检查；
6. 需要时使用安全改写，再导出 Markdown。

## 编辑与生成边界

- 模板生成器只读取当前话题关联的来源；没有足够证据时会明确说明信息不足；
- 生成内容末尾保留来源名称与链接；安全改写不会删除已有 Markdown 来源链接，也不新增来源外事实；
- 编辑检查是提示工具，不替代人工事实核验；强结论和无来源判断需要人工复核；
- 应用不绕过登录、验证码、访问控制、robots 规则或平台风控；不下载、复制或再发布来源帖的图片与视频。

## 测试

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.uv-python"
uv run pytest
```

测试覆盖演示模式启动、来源异常隔离、去重、话题聚合、草稿生成、编辑检查、安全改写、Markdown 导出及主要页面路由。

## 已知限制

- 当前话题聚合使用可解释关键词规则，不是向量语义聚类；
- 默认草稿生成器是本地证据模板，尚未接入外部 LLM；
- B 站、官方 X API 和 ComfyUI 图像生成属于阶段五可选功能，本轮未实现；
- Tailwind CSS 与 HTMX 通过 CDN 加载，离线环境需要改为本地静态资源。
