# TASK-003 任务合同：全链路过滤体育新闻（采集端 + 线上展示端）

- **task_id**: `TASK-003`
- **contract_version**: `1`
- **owner**: `fanjie`（规划与独立验收：Antigravity；研发执行：Cursor via AO）
- **base_commit**: `8a10f163d7c0a1110a616ab7b14151cded99c334`（`main` 基线；工作分支为 `feat/filter-sports-news`）
- **dependencies**: 无
- **role_bindings**:
  - `planner`: `antigravity`
  - `developer`: `cursor`（AO harness=`cursor`, model=`composer-2.5`）
  - `acceptor`: `antigravity`
- **limits**: `max_revisions=2; max_developer_runs=3; max_acceptor_runs=3; max_infrastructure_retries=1; timeout_min=60; allow_paid_api=false`

---

## 1. Objective（任务目标）

按负责人明确要求「体育新闻不需要」，在**采集选稿端**与**Cloudflare Worker 展示接口端**同步实现精准、确定性的体育新闻过滤：
1. 采集阶段（主流媒体 + Hacker News）不再收录体育赛事、球队/球员、转会、比分、联赛等体育类新闻，腾出每站最多 5 条配额给政治、科技、财经与重大社会突发新闻；
2. Worker `/api/news` 展示接口同步过滤库中已存在的历史/当日体育条目，确保上线后页面立即可见干净列表；
3. 严控误杀：不误伤含「竞赛 / 夺冠 / 联盟 / 基准得分」等字样的科技/财经/政治新闻，且若涉及重大公共安全突发事件（如伤亡、踩踏、枪击、爆炸、恐袭、预警、疏散）仍予保留。

---

## 2. Scope In（包含范围）

1. **新增确定性体育过滤模块 `collector/sports.py`**：
   - 提供 `is_sports_news(title="", original_title="", url="", summary="") -> bool`：
     - **应急安全豁免**：若标题/原标题命中重大安全突发词（如 `伤亡|遇难|踩踏|枪击|爆炸|恐袭|地震|预警|疏散|应急响应` 或英文 `casualties|stampede|shooting|explosion|terror|evacuat`），直接返回 `False`（不按体育过滤）；
     - **URL 路径特征**：解析 `urlsplit(url).path.lower()`，命中明确体育栏目路径（如 `/(?:sports?|football|soccer|nba|nfl|mlb|nhl|cricket|rugby|tennis|golf|f1|formula1|olympics|athletics|boxing|ufc|mma|baseball|basketball)(?:/|$)`）返回 `True`；
     - **英文标题词边界匹配**：使用 `\b...\b` 匹配明确体育联赛/项目/术语/球队（如 `nba`, `nfl`, `mlb`, `nhl`, `wnba`, `ncaa`, `fifa`, `uefa`, `premier league`, `champions league`, `la liga`, `serie a`, `bundesliga`, `super bowl`, `world cup`, `wimbledon`, `grand prix`, `formula 1`, `f1`, `ufc`, `mma`, `boxing`, `cricket`, `rugby`, `tennis`, `baseball`, `basketball`, `badminton`, `table tennis`, `golf`, `pga`, `nascar`, `motogp`, `marathon`, `playoffs`, `quarterback`, `touchdown`, `home run`, `goalkeeper`, `hat-trick`, `red card`, `penalty kick`, `transfer window`, `esports` 等）；
     - **中文标题关键词匹配**：匹配明确体育赛事/项目/角色词（如 `英超`, `欧冠`, `西甲`, `意甲`, `德甲`, `法甲`, `中超`, `CBA`, `NBA`, `NFL`, `MLB`, `NHL`, `UFC`, `F1`, `WTA`, `ATP`, `世预赛`, `世界杯`, `欧洲杯`, `美洲杯`, `亚洲杯`, `亚冠`, `大满贯`, `温网`, `法网`, `美网`, `澳网`, `冬奥会`, `奥运会`, `亚运会`, `全运会`, `超级碗`, `季后赛`, `总决赛`, `常规赛`, `全明星赛`, `男足`, `女足`, `男篮`, `女篮`, `男排`, `女排`, `国足`, `国乒`, `国羽`, `足球`, `篮球`, `网球`, `排球`, `乒乓球`, `羽毛球`, `棒球`, `橄榄球`, `高尔夫`, `台球`, `斯诺克`, `拳击`, `田径`, `马拉松`, `花样滑冰`, `短道速滑`, `跳水`, `体操`, `电竞`, `球星`, `球员`, `门将`, `前锋`, `后卫`, `主帅`, `主教练`, `转会`, `绝杀`, `点球`, `红牌`, `黄牌`, `加时赛`, `三分球`, `扣篮`, `篮板`, `助攻`, `帽子戏法`, `卫冕冠军`, `晋级八强`, `晋级四强`, `晋级决赛` 等）。
     - **严禁过宽泛词**：不得用单独的 `冠军`、`竞赛`、`比赛`、`联盟`、`团队`、`得分`、`赛季`、`主场` 作为独立剔除词。
2. **接入采集链路（`collector/boards.py`、`collector/hackernews.py`、`collector/polymarket.py`）**：
   - `boards.py` 在翻译前先用 `is_sports_news(original_title=original, url=link)` 快速跳过体育新闻（省翻译开销），翻译后再用 `is_sports_news(title=title, original_title=original, url=link, summary=summary)` 复核；
   - `hackernews.py` 选稿循环中同样调用 `is_sports_news` 过滤体育条目；
   - `polymarket.py` 候选事件过滤中跳过明显体育盘口（调用 `is_sports_news(original_title=title + " " + question, url=url)`），避免体育盘口干扰非体育新闻。
3. **接入 Worker 展示过滤（`worker/src/index.js`）**：
   - 在 `worker/src/index.js` 中实现与 `collector/sports.py` 口径一致的轻量确定性 `isSportsItem(row)`（同样包含应急安全豁免与 URL/中英文正则匹配），并在 `GET /api/news` 返回前过滤掉体育条目（注意为避免 `LIMIT` 被已过滤条目吃掉导致当页条数不足，SQL 查询可适当多取或按 `Math.min(n * 2, 200)` 拉取过滤后再 `.slice(0, n)`）；
   - 确保 `worker/src/index.js` 外层 `node --check` 与 `PAGE` 内嵌 `<script>` 的 `vm.Script` 门禁继续全绿。
4. **单元测试（`tests/test_sports.py`、`tests/test_worker_pulse.py`）**：
   - 新增 `tests/test_sports.py` 覆盖：
     - 典型英文/中文/URL 体育新闻（如 BBC `/sport/football/...`、NBA 季后赛、英超/欧冠、网球大满贯、F1 等）全部判定为体育并被 `boards` 跳过；
     - 非体育反例（如「中美AI算力竞赛升级」、「OpenAI新模型在数学基准测试夺冠」、「欧盟与美国就关税达成协议」、「美联储季度利率决议公布」）全部不被误杀；
     - 公共安全突发反例（如「某足球场发生踩踏事件致多人伤亡」、「马拉松赛事突遇极端天气发布紧急疏散预警」）受应急豁免不被误删；
   - 在 `tests/test_worker_pulse.py` 中新增测试：向模拟 D1 写入 1 条普通国际政治新闻 + 1 条体育新闻（如英超/NBA 或 `/sport/` 链接），验证 `GET /api/news` 只返回非体育新闻、自动隐藏体育新闻。

---

## 3. Scope Out（排除范围）

- 不删除或修改 D1 中已有历史表结构；
- 不新增第三方依赖或付费 API；
- 不执行 `git push`、`gh pr create`、`wrangler deploy`。

---

## 4. Allowed Paths

- `collector/sports.py`
- `collector/boards.py`
- `collector/hackernews.py`
- `collector/polymarket.py`
- `worker/src/index.js`
- `tests/test_sports.py`
- `tests/test_worker_pulse.py`

---

## 5. Acceptance Criteria

- **AC1**：`collector/sports.py` 正确识别中英文体育标题与 `/sport(s)/` URL，不误杀含「竞赛/夺冠/联盟/得分」的科技/财经/政治新闻，且保留含伤亡/踩踏/预警/疏散等公共安全突发新闻。
- **AC2**：`boards.py`、`hackernews.py`、`polymarket.py` 均已接入体育过滤，采集选稿不占用 5 条配额。
- **AC3**：`worker/src/index.js` 的 `GET /api/news` 自动过滤 D1 中已入库的体育新闻，同时保留正常新闻与公共安全突发新闻；`node --check` 与 `vm.Script` 内嵌脚本门禁均通过。
- **AC4**：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 全部 `OK`（退出码 `0`）。

---

## 6. Deliverables & Test Commands

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

完成后在当前 AO worktree 本地 `git commit`，并通过 `/Users/fanjie/.local/bin/ao report --done` 上报（携带 `task_id: TASK-003`、`contract_version: 1`、`attempt: 1`、`result_sha`、测试退出码、`REVIEW_REQUIRED`），随后结束回合。
