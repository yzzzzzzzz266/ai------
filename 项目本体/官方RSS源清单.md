# 官方 RSS 源清单

本清单中的 URL 已于 2026-07-28 通过 HTTP 200 和 XML 格式检测。将下列地址写入 `.env` 的 `RSS_URLS` 后，应用会在采集时只保留与 AI 前沿相关的条目；BBC、Fox 与综合新闻源中的非 AI 新闻会被现有过滤规则剔除。

## 已启用的官方来源

### AI 公司与研究机构

- OpenAI News：`https://openai.com/news/rss.xml`
- Google AI Blog：`https://blog.google/technology/ai/rss/`
- Google DeepMind Blog：`https://deepmind.google/blog/rss.xml`
- Mistral AI：`https://mistral.ai/rss.xml`
- TRAE：`https://www.trae.ai/rss.xml`
- Microsoft Research：`https://www.microsoft.com/en-us/research/feed/`
- NVIDIA Developer Blog：`https://developer.nvidia.com/blog/feed/`
- Hugging Face Blog：`https://huggingface.co/blog/feed.xml`
- AWS Machine Learning Blog：`https://aws.amazon.com/blogs/machine-learning/feed/`
- Google Research Blog：`https://research.google/blog/rss/`
- Together AI Blog：`https://www.together.ai/blog/rss.xml`

### 国际新闻

- BBC Technology：`https://feeds.bbci.co.uk/news/technology/rss.xml`
- BBC World：`https://feeds.bbci.co.uk/news/world/rss.xml`
- Fox News Tech：`https://moxie.foxnews.com/google-publisher/tech.xml`
- Fox News Science：`https://moxie.foxnews.com/google-publisher/science.xml`
- TechCrunch Artificial Intelligence：`https://techcrunch.com/category/artificial-intelligence/feed/`
- MIT Technology Review Artificial Intelligence：`https://www.technologyreview.com/topic/artificial-intelligence/feed/`

### 中国新闻

- China Daily China：`https://www.chinadaily.com.cn/rss/china_rss.xml`
- China Daily World：`https://www.chinadaily.com.cn/rss/world_rss.xml`
- 新华社 Science & Technology：`https://www.xinhuanet.com/english/rss/scirss.xml`

## 暂不加入的站点

以下站点在本次检查中没有返回可解析的官方 RSS/Atom XML，因此没有使用第三方转换或网页抓取替代：Anthropic、Meta AI、DeepSeek、豆包。它们发布官方 RSS 后可再加入；目前仍可通过其官方网站或公告页人工核验。

## 使用方式

`.env` 已预置以上 URL。修改后重启服务，再点击“立即采集”；单个 RSS 源出现 HTTP 错误或 XML 解析错误时会被跳过，不会中断其余 RSS 源的采集。

## CSDN 订阅白名单

以下为经 HTTP 200 与 XML 解析验证的公开 CSDN 博客 RSS，已于 2026-07-26 加入本地 `.env`。这些是个人公开订阅源，不代表 CSDN 官方观点；采集仍遵守近 7 天、AI 相关性过滤和去重规则。

- 攻城狮7号：`https://blog.csdn.net/linshantang/rss/list`
- 吃果冻不吐果冻皮：`https://blog.csdn.net/scgaliguodong123_/rss/list`
- 一个处女座的程序猿：`https://blog.csdn.net/qq_41185868/rss/list`
- sinat_39620217：`https://blog.csdn.net/sinat_39620217/rss/list`

`AMiner2006` 与“五道口纳什”的 RSS 地址虽能返回 HTTP 200，但当前内容无法作为规范 XML 解析，因此暂不接入。其余名单尚未确认唯一的 CSDN 账号；提供其博客主页链接或准确账号名后，可以继续验证并加入白名单。
