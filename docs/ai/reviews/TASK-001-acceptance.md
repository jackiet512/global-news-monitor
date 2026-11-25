# TASK-001 独立验收报告

- **task_id**: `TASK-001`
- **contract_version**: `1`
- **developer**: Cursor（AO session `global-news-monitor-1`, model `composer-2.5`）
- **acceptor**: Antigravity（独立代码审查 + 独立测试与对抗反例复跑）
- **base_commit**: `c5421fdbe4b8959de828bb454feeb9be6d894108`（父主线 `main` 基线：`c1e7f4a5a8dd86a79465762972087b05c7930849`）
- **attempt_1_sha**: `f00f58f3d4f18c552578724b264f2ff9d4cf7d8b` → `changes_requested`（集中返修 5 项，`rework: 1/2`）
- **accepted_attempt**: `2`
- **accepted_head_sha**: `a2ba873fdd15e0f58a2c509aa66f260cadd3f61f`
- **verdict**: `passed`
- **验收时间**: `2026-11-25T08:43:00Z`

---

## 1. 返修闭环核验（Attempt 1 → Attempt 2）

| 编号 | Attempt 1 发现问题 | Attempt 2 修复核验结果 |
|---|---|---|
| 1 | `boards.py` 未保存 `original_title` 且中文源无英文检索词，实测主流媒体 Polymarket 命中为 `None` | 已修复：`boards.py` 保存 `original_title` 与 `en_title`，`community.py` 提供带内存缓存的免密钥 `to_english()`，中英文源均能生成有效英文检索词并匹配盘口；`hackernews.py` 时间戳统一为 `+08:00` |
| 2 | `worker/src/index.js` 中 `fetchPolymarket` 为 `return null` 空桩、`extractTerms` 返回数组导致逗号拼接、`/api/pulse` 泄漏内部 `hn_meta` | 已修复：实装 `fetchPolymarket(query)` 请求 Gamma API 并做停用词过滤与双实词匹配；无匹配时返回 `source_status.polymarket = "empty"`；`cleanPulseCommunity()` 净化 HTTP 响应且 D1 回写保留 `hn_meta` |
| 3 | `reading.py` 的 `_url_allowed` 布尔语义反转（`ftp://` 返回 `False` 未被拦截，回环 IP 返回 `True`） | 已修复：`_url_allowed(link, require_https=True)` 统一为白名单布尔语义，严格阻断非 `https`、内网/回环/链路本地/保留/多播/未指定 IP 与对应 DNS 解析结果 |
| 4 | `hackernews.py` 评论项缺少 `title` 与 `discussion_url` 导致前端渲染出空标题与伪 `0分` | 已修复：`community.hn` 首项包含结构化标题、真实分数、评论数、讨论链接与 `@author` 评论摘录，前端 `renderPulse()` 同步加固兜底 |
| 5 | `community.py` 中 `as_completed(..., timeout=budget)` 超时抛未捕获 `TimeoutError` | 已修复：全量生成 `query_terms`，预采集限制 `max_items=12`，捕获 `FuturesTimeoutError` 并执行 `pool.shutdown(wait=False, cancel_futures=True)` |

---

## 2. 合同条款逐条验收结果（AC1–AC6）

- **AC1（HN 热榜选稿与安全正文补全）**：`passed`
  - 核查 `collector/hackernews.py` 与 `collector/reading.py`，独立复测公网 IP `https://93.184.216.34/story` 放行，而 `http://`、`ftp://`、`file://`、`javascript:`、`localhost`、`127.0.0.1`、`192.168.1.1`、`10.0.0.1`、`169.254.169.254` 全部阻断；无外链帖子正确回退 `news.ycombinator.com/item?id=...`。
- **AC2（Polymarket 双格式解析与防泛词误配）**：`passed`
  - 核查 `collector/polymarket.py`，JSON 字符串与原生数组格式的 `outcomes`/`outcomePrices` 均正确解析百分比与成交额；仅含 `"US President Will Win in 2026"`、`"Will AI change the world in 2026"` 等泛词的新闻在 Python 端与 Worker 端均返回 `None`（零误挂）。
- **AC3（社区脉络聚合与异常隔离）**：`passed`
  - 核查 `collector/community.py` 与 `collector/boards.py`，模拟 HTTP 403/429 及 25 条慢请求超出 `budget=0.2s` 时，`enrich_items()` 在 `0.21s` 内安全返回且全部条目均保有 `query_terms`，不抛未捕获异常。
- **AC4（D1 迁移与 Worker `/api/ingest`、`/api/news`、`/api/pulse` 闭环）**：`passed`
  - 独立运行 Node `node:sqlite` 内存库对抗测试：`0001_init.sql` + `0002_context.sql` 迁移通过；`/api/pulse` 非法指纹返回 `400`、未知指纹返回 `404`、动态补拉 Polymarket Gamma 盘口成功持久化至 D1 且不覆盖原 `hn_meta`、30 分钟缓存命中返回 `cached: true`。
- **AC5（前端标签、脉络抽屉与防 XSS）**：`passed`
  - `node --check worker/src/index.js` 退出码 `0`；主列表渲染 `.pmcap` 概率胶囊与 `.hnmeta` 热度信息，卡片内支持展开/收起 `.pulse-drawer` 并防并发重复拉取；注入 `<script>alert(1)</script>` 与 `javascript:alert(1)` 验证均被 `esc()` 与 `safeHref()` 阻断。
- **AC6（离线单元测试全绿）**：`passed`
  - 工作目录：`/Users/fanjie/.ao/data/worktrees/global-news-monitor/global-news-monitor-1`
  - 命令：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`
  - 结果：28 项测试全部 `OK`（真实退出码 `0`）；独立对抗测试套件 `NODE_ADVERSARIAL_ALL_PASSED`（真实退出码 `0`）。

---

## 3. 边界声明

- 本次交付仅集成至本地隔离建设分支 `collab/hn-polymarket-community`，未推送远端、未合并 `main`、未执行 `wrangler deploy`、未触碰生产 D1 数据库。
