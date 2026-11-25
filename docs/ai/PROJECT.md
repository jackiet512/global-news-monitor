# PROJECT — 全球新闻中心（global-news-monitor）

## 目标

从海内外权威新闻源及免密钥公开社区/预测市场接口自动收录国际政治、人工智能与科技、全球经济金融、社会与突发事件，提供中文摘要、跨站同事件去重、Polymarket 预测市场概率标签与 HN/Reddit 社区讨论脉络。

## 范围

### 包含
- 定时与手动触发采集引擎（`collector/`）：主流媒体选稿、跨站事件去重、正文与配图抽取、中文化翻译
- 免密钥公开信号扩展（复用 `last30days-skill` 免 Key 子模块思路）：Hacker News 科技热榜（Algolia API）、Polymarket 预测市场概率匹配（Gamma API）、HN/Reddit 社区讨论脉络采集与按需查询
- Cloudflare Worker + D1 存储与前端单页阅读界面（`worker/`、`migrations/`）
- 确定性单元测试（`tests/`）与 CI 质量门禁（`.github/workflows/quality.yml`）

### 不含
- 付费第三方爬虫 API（如 ScrapeCreators、xAI/OpenAI 付费接口）或需登录态 Cookie 的脆弱抓取
- 大模型实时生成摘要/评论（保持零 LLM 运行开销）
- 未经授权的自动部署、主线合并或生产库写入

## 架构

```text
GitHub Actions (每小时 07/37 分) ──► collector/collect.py
                                      ├─ boards.py / events.py / reading.py (10 大主流媒体 + 原文补全)
                                      └─ Hacker News / Polymarket / Reddit 免 Key 信号模块
                                             │ POST /api/ingest (Bearer INGEST_TOKEN)
                                             ▼
Cloudflare Worker (worker/src/index.js) ◄──► Cloudflare D1 (SQLite: news_items, news_reading, news_context, reports, source_runs)
       ├─ Cron Fallback (每小时 20/50 分检查 GitHub Actions 超 45 分钟兜底触发)
       └─ 响应式中文阅读前端 + /api/news + /api/reports + /api/pulse + /api/collect
```

## 关键目录

| 路径 | 用途 |
|---|---|
| `collector/` | Python 采集、跨站事件去重、翻译、正文抽取及 HN/Polymarket/社区脉络模块 |
| `worker/src/` | Cloudflare Worker 接口、定时兜底、编辑过滤词表（`editorial.json`）与内嵌前端页面 |
| `migrations/` | Cloudflare D1 SQLite 表结构迁移文件 |
| `tests/` | Python `unittest` 单元测试套件 |
| `docs/` | 部署说明（`CLOUDFLARE_SETUP.md`）与 AI 协作文档（`docs/ai/`） |

## 运行与测试

```sh
python3 -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
node --check worker/src/index.js
```

## 限制 / 禁止操作

- 采集全流程须在 GitHub Actions 8 分钟超时内稳定完成；任一外部公开接口超时/限流（如 HTTP 429/403/5xx）须优雅降级，不得阻断主新闻采集入库。
- 严禁硬编码或提交 `INGEST_TOKEN`、`GITHUB_ACTIONS_TOKEN` 等密钥。
- 未经负责人书面授权，禁止 `git push`、合并到 `main`、执行 `npx wrangler deploy` 或直接写入远端生产 D1。
