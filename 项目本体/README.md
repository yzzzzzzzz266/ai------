# AI Radar

AI Radar 是面向 AI 内容创作者的本地信息工作台：采集公开 AI 前沿信号、按规则聚合话题、保留可追溯来源，并提供新闻阅读、资料整理、证据分析和草稿生成。

## 核心功能

- **前沿 AI 新闻过滤**：只保留同时命中 AI 与模型发布、推理、智能体、多模态、评测、开源、论文或 API 等前沿信号的公开来源。
- **公开来源采集**：arXiv、GitHub、Hacker News，以及 `.env` 中配置的公开 RSS。
- **热点聚合**：按可解释关键词规则将来源聚合为话题，计算热度和新鲜度，并保留每条证据的原始链接、作者、发布时间和抓取时间。
- **AI 工作台**：
  - AI 读新闻：提取主要内容、AI 前沿关联和待核验信息；
  - 生成资料包：整理资料脉络、来源和后续追问；
  - AI 证据分析：输出“可确认事实 / 谨慎推断 / 未知与风险 / 下一步核验”，不展示模型内部推理链。
- **内容创作**：生成可编辑的新闻快讯、编辑解读、创作者选题和技术拆解草稿，保留 Markdown 来源区块。
- **编辑检查**：提示无来源强判断、空泛表达、重复连接词和需人工复核的强结论。

## 数据真实性

应用不再创建或保留演示数据。页面中的来源均标注为“公开采集”，并保留原始 URL。请在写作前打开原始链接完成最终事实核验。

## AI Provider

默认无需 API Key，使用**本地规则分析**整理现有来源，并在页面中明确标注“本地规则分析（未配置模型 API）”。

如需模型驱动的摘要、资料包和证据分析，复制 `.env.example` 为 `.env`，填写：

```env
OPENAI_API_KEY=你的密钥
OPENAI_MODEL=gpt-5.6
# See 权威来源配置说明.md for source weights and authority allowlists.
```

配置后，AI 工作台使用 OpenAI Responses API。服务启动时会验证 `OPENAI_MODEL` 是否可由当前 API 项目访问；若不可用，启动会给出模型名称、项目权限与替换模型的明确提示。模型输出仍会附加应用生成的“数据来源”区块；模型不得替代人工事实核验。

## 启动

在 `项目本体` 目录执行：

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.uv-python"
uv run uvicorn app.main:app --reload --port 8002
```

打开 `http://127.0.0.1:8002`。

## 使用流程

1. 点击“立即采集”获取公开 AI 前沿信号；
2. 点击“生成热点”更新话题聚合；
3. 打开话题详情，查看来源证据与原始链接；
4. 点击“AI 读新闻”提取单条新闻主旨；或进入“AI 工作台”生成资料包、证据分析；
5. 点击“生成证据草稿”，编辑并导出 Markdown。

## 配置

| 变量 | 用途 |
| --- | --- |
| `DATABASE_URL` | SQLite 数据库地址 |
| `RSS_URLS` | 一个或多个公开 RSS 地址，逗号或换行分隔 |
| `GITHUB_TOKEN` | 可选，用于提高 GitHub API 请求额度 |
| `COLLECTION_INTERVAL_MINUTES` | APScheduler 采集间隔，最小 1 分钟 |
| `SCHEDULER_ENABLED` | 是否启用定时采集 |
| `OPENAI_API_KEY` | 可选，启用模型驱动 AI 工作台 |
| `OPENAI_MODEL` | 要使用的模型名称；启动时验证当前 API 项目是否可访问 |

## 合规边界与限制

- 不绕过登录、验证码、访问控制、robots 规则或平台风控；
- 不下载、复制或再发布来源图片和视频；
- 单个来源错误会显示状态，但不会中断其他来源；
- AI 结果只基于当前关联来源；信息不足时应明确说明；
- 当前聚合使用关键词规则，不是向量语义聚类；
- X 与 B 站采集仅在配置对应白名单后启用，详见 `权威来源配置说明.md`；ComfyUI 图像生成尚未实现。

## 测试

```powershell
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\.uv-python"
uv run pytest
```
