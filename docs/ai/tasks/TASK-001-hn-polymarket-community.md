# TASK-001 任务合同：主列表接入 HN 热榜与 Polymarket 概率标签 + 展开社区讨论脉络

- **task_id**: `TASK-001`
- **contract_version**: `1`
- **owner**: `fanjie`（规划与独立验收：Antigravity；研发执行：Cursor via AO）
- **base_commit**: `c1e7f4a5a8dd86a79465762972087b05c7930849`（父主线基线；工作分支基线为 `collab/hn-polymarket-community` 初始化提交）
- **dependencies**: 无前置未完成任务；Python 依赖仅使用标准库及现有 `requirements.txt`（不新增需编译或付费 SDK 依赖）
- **role_bindings**:
  - `planner`: `antigravity`
  - `developer`: `cursor`（AO harness=`cursor`, model=`composer-2.5`）
  - `acceptor`: `antigravity`（独立代码审查 + 独立测试与反例复跑）
- **limits**: `max_revisions=2; max_developer_runs=3; max_acceptor_runs=3; max_infrastructure_retries=1; timeout_min=60; allow_paid_api=false`

---

## 1. Objective（任务目标）

借鉴 `mvanhorn/last30days-skill` 中免密钥（Keyless）公开数据源与互动热度加权设计，在**零付费 API、零大模型推理成本、不破坏现有 10 大主流媒体采集稳定性**的前提下，为「全球新闻中心」完整交付以下三项能力：

1. **主列表接入 Hacker News 科技热榜**：每轮从 Algolia HN 公开接口精选最多 5 条高热度技术报道/讨论并中文化，补强 `AI与科技` 栏目的一手技术信号；
2. **主列表自动挂载 Polymarket 预测市场概率标签**：从 Polymarket Gamma 公开只读接口获取活跃事件盘口，经高精度双语词元匹配后，在相关政治/财经/科技新闻卡片上展示实时预测概率胶囊标签；
3. **支持单条新闻展开「社区讨论脉络 + 预测市场风向」**：结合采集期预关联数据与 Cloudflare Worker 新增的 `GET /api/pulse?fingerprint=...` 按需查询（带 D1 `news_context` 缓存与超时/限流隔离），在前端新闻卡片内点击即可展开查看对应的 Polymarket 盘口详情、Hacker News 讨论帖与高赞观点摘录、以及 Reddit 相关版块热议。

---

## 2. Scope In（包含范围与技术规范）

### 2.1 Hacker News 热榜采集（`collector/hackernews.py` + `collector/reading.py` 适配）
- 调用免密钥接口 `https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=35`（若返回为空，可回退 `https://hn.algolia.com/api/v1/search?tags=story&numericFilters=created_at_i>{cutoff}&hitsPerPage=35`；注意**严禁**在 Algolia `numericFilters` 中传入未索引的 `points>` 以免触发 HTTP 400，统一在 Python 侧过滤低分项并按互动热度如 `points + 2 * num_comments` 排序）。
- 每轮最多入选 **5 条**（遵循站点 `每站最多五条` 规则）：
  - 有合法公网 `https?://` 外链时使用该外链作为 `url`，无外链帖子（如 `Ask HN` / `Show HN`）回退至 `https://news.ycombinator.com/item?id={objectID}`；
  - `source_name` 固定为 `"Hacker News"`，默认 `category="AI与科技"`（若标题明显匹配国际政治/全球经济金融规则亦可按规则归类，科技与开发话题统一归入 `"AI与科技"`）；
  - 保留原始英文标题 `original_title` 供盘口与社区检索词提取使用，展示 `title` 经既有 `chinese()` 译为中文；
  - 附带 `hn_meta`（`object_id`, `points`, `num_comments`, `discussion_url`），并对入选的最多 5 条 HN 故事可选拉取 `https://hn.algolia.com/api/v1/items/{objectID}` 前 2 条高信息量顶级评论纯文本摘录（清洗 HTML、截断过长文本并可译为中文摘要）存入该条目的 `community.hn` 中。
- **修复/扩展 `collector/reading.py` 的 `enrich()`**：
  - 现有 `enrich()` 第 44 行直接访问 `sites[item["source_name"]][0]`，对不在 `SITES` 字典中的 `"Hacker News"` 会抛 `KeyError` 或跳过所有外链；
  - 须支持 `"Hacker News"` 条目的公网 `https://` 外链安全抓取正文预览与配图，同时**严格拦截**非 `http/https` 协议、`localhost`、回环/私有/链路本地 IP 地址（防 SSRF）；若外链位于 `news.ycombinator.com` 或无法提取长正文，优雅保留 HN 讨论摘要而不报错。

### 2.2 Polymarket 预测市场概率匹配（`collector/polymarket.py`）
- 调用免密钥只读 Gamma API：`https://gamma-api.polymarket.com/events?active=true&closed=false&limit=80`（设置合理超时如 `<=10s`）。
- 解析每个 `event` 下的 `markets`：
  - **必须兼容** `outcomes` 与 `outcomePrices` 为 **JSON 编码字符串**（如 `'["Yes", "No"]'`、`'["0.68", "0.32"]'`）或原生 `list` 两种格式；跳过价格缺失、长度不匹配、已关闭或全 0 的无效子市场。
  - 计算主展示概率：二元 `Yes/No` 盘口优先提取 `"Yes"` 概率百分比（`round(price * 100)`，如 `68%`）；多选项盘口提取当前最高概率选项名称及百分比；提取事件总成交量（`volume` 或 `volume24hr`）并格式化为易读字符串（如 `$1.2M` / `$85K`）。
  - 生成安全盘口链接 `https://polymarket.com/event/{slug}`。
- **高精度确定性匹配算法**：
  - 构建严格的英文与中文泛词停用词表（必须排除如 `will, the, and, for, with, what, when, before, after, 2025, 2026, 2027, president, market, world, global, news, says, report, china, united, states, us, ai, model, new, year, month` 等单独泛词触发匹配的情况——专有实体须与其他有效实词组合命中）。
  - 对英文源新闻直接使用其翻译前的 `original_title` 词元；对中文源新闻（新华网、人民日报、凤凰卫视）可提取英文缩写/专名或借助反向英文词元/盘口标题中文译文二元词组交叉匹配。
  - 仅当有效非停用词重合数 `>= 2` 且重合度分数达到阈值时才绑定最佳匹配盘口，挂载结构化字典：
    ```json
    {
      "event_title": "盘口中文标题（或双语简述）",
      "question": "具体子市场问题（中文）",
      "outcome": "Yes",
      "probability": 68,
      "volume_text": "$1.2M",
      "url": "https://polymarket.com/event/..."
    }
    ```
  - 未命中时设为 `None`，严禁强行凑数匹配。

### 2.3 社区讨论脉络采集与主链路整合（`collector/community.py`、`collector/boards.py`、`collector/collect.py`）
- 实现 `collector/community.py`：
  - 从新闻条目提取精炼检索词 `query_terms`（优先英文核心专名/实词，控制在 3–6 个核心词，提升 HN 与 Reddit 搜索召回率）；
  - **HN 讨论检索**：`https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=5&query=...`，提取标题（可附中文译文或清晰双语）、`points`、`num_comments`、`discussion_url`（`https://news.ycombinator.com/item?id=...`）与外链；
  - **Reddit 公开讨论检索**：`https://www.reddit.com/search.json?q=...&sort=relevance&t=month&limit=5&raw_json=1`（带合规自定义 `User-Agent` 与 `<=8s` 超时），提取 `subreddit`（如 `r/worldnews`）、标题、`score`、`num_comments`、`url`（`https://www.reddit.com{permalink}`）。
  - **严格故障与耗时隔离**：使用线程池控制并发与单轮最大检索预算，保证整轮 `collect.py` 在 GitHub Actions **8 分钟限制**内留有充足余量；当 HN、Polymarket 或 Reddit 任一接口超时、连接失败或返回 HTTP 403/429/5xx 时，仅记录非致命源警告或标记 `source_status` 降级，**绝不中断主流媒体新闻的采集与入库**。
- `boards.py` / `collect.py` 输出的每个 `item` 向后兼容原有全部字段，并新增可选字段：`polymarket`、`community`、`query_terms`（以及 HN 条目的 `hn_meta`）。

### 2.4 D1 迁移、Worker 接口与前端抽屉交互（`migrations/0002_context.sql`、`worker/src/index.js`）
- **新增迁移文件 `migrations/0002_context.sql`**：创建 `news_context` 表（`fingerprint TEXT PRIMARY KEY`, `polymarket_json TEXT`, `community_json TEXT`, `query_terms TEXT`, `updated_at TEXT NOT NULL`）及必要索引；Worker 内同步保留 `CREATE TABLE IF NOT EXISTS news_context ...` 以兼容未手动跑新迁移的环境。
- **更新 `POST /api/ingest`**：
  - 兼容接收新字段 `polymarket`、`community`、`query_terms`、`hn_meta`（旧格式 payload 仍 100% 正常入库）；
  - 在同一 `db.batch` 中安全写入/更新 `news_context`（序列化前校验类型并限制单字段体积，防止恶意超大包）。
- **更新 `GET /api/news`**：
  - `LEFT JOIN news_context nc ON nc.fingerprint = ni.fingerprint`，在返回条目中安全 JSON 解析并附带 `polymarket`、`community`、`query_terms`（解析失败时安全回退 `null` / 空结构，绝不导致 `/api/news` 500）。
- **新增 `GET /api/pulse?fingerprint=<64位十六进制>`**：
  - 校验 `fingerprint` 格式（不合法返回 `400 invalid_fingerprint`）；查询 `news_items` + `news_context`，若条目不存在返回 `404 not_found`；
  - 若 `news_context` 已有未过期（如 30 分钟内更新且含社区结果）缓存且未传 `refresh=1`，直接返回缓存数据并标记 `cached: true`；
  - 否则基于 `query_terms`（无则从标题提取关键词）通过 `Promise.allSettled` 并发请求免密钥公开接口（HN Algolia API、Reddit `search.json`、若尚无盘口则补充 Polymarket Gamma API，单源 `AbortSignal.timeout(5000)`），合并已有预采集数据后回写 `news_context` 并返回：
    `{ ok: true, fingerprint, cached: false, polymarket, community: { hn: [...], reddit: [...] }, source_status: { hn: "ok"|"empty"|"unavailable", reddit: ..., polymarket: ... }, updated_at }`。
- **升级前端阅读界面（`worker/src/index.js` 内 `PAGE`）**：
  - **主列表展示**：
    - 命中 `polymarket` 的新闻卡片，在标题下方或标签栏渲染简洁醒目的**预测市场胶囊标签**（例如：`预测市场 · Yes 68% · <盘口简述> ↗`，带成交量提示与安全外链）；
    - 来源为 `Hacker News`（或具备 `hn_meta`）的卡片，展示热度信息（如 `Hacker News · 280分 · 95评`）；
  - **「社区与市场脉络」折叠抽屉**：
    - 每张新闻卡片底部提供交互按钮（如 `社区与市场脉络`；若预采集已有盘口或讨论条数，可显示徽标如 `社区与市场脉络 (4)`）；
    - 点击展开卡片内抽屉：若需拉取最新讨论则请求 `/api/pulse?fingerprint=...`（展示加载状态，防止连点重复请求）；
    - 抽屉内清晰分区展示：**Polymarket 预测风向**、**Hacker News 社区讨论**（含讨论链接及摘录）、**Reddit 社区热议**（含 `r/...` 版块、赞数、评论数、链接）；若某源暂无相关讨论或公共接口临时限流，显示清晰的中文状态说明；
    - **XSS 与外链安全**：所有插入 HTML 的动态文本必须经 `esc()` 转义，所有 `href` 必须校验 `/^https?:\/\//i` 并带 `target="_blank" rel="noopener noreferrer"`。
- **文档同步**：更新 `README.md` 与 `docs/CLOUDFLARE_SETUP.md`（补充 `0002_context.sql` 迁移命令与新增功能说明）。

---

## 3. Scope Out（排除范围）

- 严禁引入任何需付费、需注册 API Key 或登录 Cookie 的服务（不含 ScrapeCreators、xAI、OpenAI、X/Twitter、TikTok、Instagram）。
- 严禁修改 `.github/workflows/collect.yml` 的调度频率或双重兜底触发逻辑。
- 严禁修改 `docs/ai/STATUS.md` 中的验收结论为 `accepted`（由验收者独立验收后更新）。
- 严禁执行 `git push`、`gh pr create`、`npx wrangler deploy` 或连接远端生产 D1 数据库。

---

## 4. Allowed Paths（允许修改/新增路径）

- `collector/collect.py`
- `collector/boards.py`
- `collector/reading.py`
- `collector/hackernews.py`
- `collector/polymarket.py`
- `collector/community.py`
- `migrations/0002_context.sql`
- `worker/src/index.js`
- `README.md`
- `docs/CLOUDFLARE_SETUP.md`
- `tests/test_collector.py`
- `tests/test_hackernews.py`
- `tests/test_polymarket.py`
- `tests/test_community.py`
- `tests/test_worker_pulse.py`

（严禁修改上述列表以外的仓库文件，严禁提交 `.DS_Store` 或 `__pycache__`。）

---

## 5. Deliverables（交付物要求）

1. 在 AO 分配的隔离 worktree 分支内完成全部代码、迁移脚本、文档与离线单元测试开发；
2. 完成本地 `git commit`（提交说明清晰关联 `TASK-001`）；
3. 使用 `/Users/fanjie/.local/bin/ao report --done` 提交结构化交付报告，正文中明确包含：
   - `task_id: TASK-001`
   - `contract_version: 1`
   - `attempt: 1`
   - `result_sha: <本地 commit 完整 40 位 SHA>`
   - 测试命令、工作目录与真实退出码汇总
   - `REVIEW_REQUIRED`
4. 提交报告后立即结束当前回合，不继续追加未授权改动。

---

## 6. Acceptance Criteria（逐条可验证验收条件）

- **AC1（HN 热榜选稿与安全正文补全）**：`hackernews.py` 正确解析 Algolia HN 响应、过滤重复项、每轮最多返回 5 条且无外链条目正确回退至 `news.ycombinator.com/item?id=...`；`reading.py` 支持 `Hacker News` 合法公网 `https://` 外链且拒绝内网/回环/非 http(s) 地址，不抛 `KeyError`。
- **AC2（Polymarket 双格式解析与防泛词误配）**：`polymarket.py` 对 JSON 字符串与原生数组格式的 `outcomes`/`outcomePrices` 均能正确解析百分比与成交额；同事件测试样本能准确命中盘口，仅含 `"US"`, `"Will"`, `"AI"`, `"President"`, `"2026"` 等泛词的不相关新闻返回 `None`（零误挂）。
- **AC3（社区脉络聚合与异常隔离）**：`community.py` 正确解析 HN Algolia 与 Reddit JSON 讨论结构；模拟 HTTP 403/429/500、超时或坏 JSON 时不抛未捕获异常，主采集 `collect()` 仍正常产出主流媒体条目。
- **AC4（D1 迁移与 Worker `/api/ingest`、`/api/news`、`/api/pulse` 正确性）**：`migrations/0002_context.sql` 可在内存 SQLite 中与 `0001_init.sql` 连续执行无误；`/api/ingest` 兼容新旧 payload 写入 `news_context`；`/api/news` 正确关联返回 `polymarket` 与 `community`；`/api/pulse` 对非法指纹返回 `400`、未知指纹返回 `404`、命中缓存返回 `cached: true`、未命中缓存并发拉取并回写。
- **AC5（前端渲染、交互与防 XSS）**：`node --check worker/src/index.js` 通过；前端包含 Polymarket 概率胶囊、HN 热度展示与「社区与市场脉络」展开/收起及 `/api/pulse` 加载逻辑；所有动态内容均经过 `esc()` 转义且外链限制为 `https?://`。
- **AC6（离线单元测试全绿）**：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 在无外网环境下全部 `OK`（退出码 `0`），覆盖上述 AC1–AC5 的正向路径与边界/反例（包括利用 Node 子进程或内嵌模拟 D1 验证 Worker `/api/ingest`、`/api/news`、`/api/pulse` 真实执行行为）。

---

## 7. Test Commands（标准验证命令）

> 执行约束：测试命令统一使用 `python3`（勿用裸 `python`），禁止在终端执行 `curl`、`wget`、`git push`、`git reset`、`git clean`、`rm -rf`。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

（Node 语法与 Worker 逻辑校验可通过 `tests/test_worker_pulse.py` 内调用 `subprocess.run(["node", "--check", "worker/src/index.js"], ...)` 及 Node 脚本加载测试一并验证，确保单条 `python3 -m unittest` 命令即可覆盖前后端全链路退出码。）
