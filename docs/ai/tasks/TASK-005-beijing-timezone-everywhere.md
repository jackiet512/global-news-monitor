# TASK-005 任务合同：全链路统一转换与输出北京时区（`+08:00`）

- **task_id**: `TASK-005`
- **contract_version**: `1`
- **owner**: `fanjie`（规划与独立验收：Antigravity；研发执行：Cursor via AO）
- **base_commit**: `8f746188c4bc59965f03c609030382746f7893ed`（`main` 基线；工作分支为 `feat/beijing-timezone-everywhere`）
- **dependencies**: 无
- **role_bindings**:
  - `planner`: `antigravity`
  - `developer`: `cursor`（AO harness=`cursor`, model=`composer-2.5`）
  - `acceptor`: `antigravity`
- **limits**: `max_revisions=2; max_developer_runs=3; max_acceptor_runs=3; max_infrastructure_retries=1; timeout_min=60; allow_paid_api=false`

---

## 1. Objective（任务目标）

经核实最新线上采集产物（run `45957840662`）：条目 `published_at`/`collected_at` 已转 `+08:00`，但 `collector/collect.py` 生成的 `report["run_at"]` 仍为 UTC（`+00:00`），且 Cloudflare Worker 的 `/api/ingest`、`/api/reports`、`/api/news`、`/api/pulse` 仍存在未归一化历史 UTC/`Z`/SQLite `created_at`、`/api/reports` 按字符串 `ORDER BY run_at DESC` 排序可能与 `+08:00` 混排乱序、`clusterNewsItems` 合并后未按最终主条目时间重排等问题。

本任务目标是将**采集器输出、D1 写入、API 查询返回（含历史记录）、排序逻辑与前端展示**全链路统一为精确的北京时区（`YYYY-MM-DDTHH:MM:SS+08:00`）。

---

## 2. Scope In（包含范围）

### 2.1 Python 采集端统一北京时区（`collector/collect.py`、`collector/boards.py`、`collector/hackernews.py`）
- **`collector/collect.py`**：
  - 定义 `BJ = timezone(timedelta(hours=8))` 与确定性转换函数 `to_beijing_iso(value)`：
    - 支持 `Z`、`+00:00`、任意合法时区偏移（如 `-05:00`）、以及无时区偏移的 naive ISO / SQLite `YYYY-MM-DD HH:MM:SS`（按 UTC 解释），统一转换并格式化为 `YYYY-MM-DDTHH:MM:SS+08:00`（`timespec="seconds"`）；
    - 对空值或非法时间字符串安全返回 `""`（或原空值），不抛未捕获异常。
  - `report["run_at"]` 改为 `datetime.now(BJ).isoformat(timespec="seconds")`（严格 `+08:00`）。
  - 对所有 `items` 的 `published_at` 与 `collected_at` 调用 `to_beijing_iso()` 统一归一化为 `YYYY-MM-DDTHH:MM:SS+08:00`，并按真实时间（parsed timestamp / 归一化 ISO 串）倒序排列 `items`。
- **`collector/boards.py` & `collector/hackernews.py`**：
  - 所有生成 `published_at`、`collected_at` 的位置统一使用 `timespec="seconds"` 的 `+08:00` ISO 格式（`YYYY-MM-DDTHH:MM:SS+08:00`），消除毫秒与格式混杂。

### 2.2 Worker 存储与全 API 接口统一北京时区（`worker/src/index.js`）
- **新增确定性时间转换函数 `toBeijingIso(value)`**：
  - 接受毫秒时间戳、合法 ISO 字符串（含 `Z`、`+00:00`、`-05:00`、`+08:00`）或 SQLite 默认格式 `YYYY-MM-DD HH:MM:SS`（无时区时按 UTC 解释，先规范化为 `YYYY-MM-DDTHH:MM:SSZ` 再解析）；
  - 精确加上 8 小时后使用 UTC getter 格式化为固定 25 字符 `YYYY-MM-DDTHH:MM:SS+08:00`（严禁依赖受运行环境 locale 影响的 `toLocaleString`）；无效输入返回 `value || null`。
- **`POST /api/ingest`**：
  - 对 `b.run_at`、每条 `x.published_at`、`x.collected_at` 经 `toBeijingIso()` 归一化后再写入 `reports`、`news_items`、`news_context`、`source_runs`（向后兼容旧格式入参，即使旧脚本传 UTC `Z` 也能自动转为 `+08:00` 入库）。
- **`GET /api/reports`**：
  - SQL 查询改用 `ORDER BY julianday(run_at) DESC LIMIT 200`（解决历史 `+00:00` 与新 `+08:00` 字符串混排乱序隐患）；
  - 返回的每条报告记录中 `run_at` 与 `created_at` 均经 `toBeijingIso()` 转为 `+08:00`。
- **`GET /api/news`**：
  - 返回的每条新闻记录中 `published_at`、`collected_at`、`created_at` 以及 `related_sources[]` 中每项的 `published_at` 均经 `toBeijingIso()` 转为 `+08:00`；
  - `clusterNewsItems` 合并完成后，按主条目的 `Date.parse(b.published_at || b.collected_at) - Date.parse(a.published_at || a.collected_at)` 严格倒序排列再 `.slice(0, n)`。
- **`GET /api/pulse`**：
  - 写入与返回的 `updated_at` 统一使用 `toBeijingIso(Date.now())`（`+08:00`）；命中缓存返回时同样对 `row.updated_at` 经过 `toBeijingIso()` 归一化。
- **前端 `PAGE`**：
  - 保持 `timeZone: 'Asia/Shanghai'` 渲染卡片与采集记录时间；
  - 若在 `related-sources` 中展示来源时间或保留简洁展示，确保所有时间经 `date()` 渲染，且严禁在模板字符串中引入裸 `\/` 正则字面量（必须持续通过 `test_inline_script_vm_gate`）。

### 2.3 离线单元测试（`tests/test_collector.py`、`tests/test_worker_pulse.py`）
- **`tests/test_collector.py`**：
  - 覆盖 `to_beijing_iso` 对 `Z`、`+00:00`、`-05:00`、`+08:00`、SQLite naive 时间串、空值/非法字符串的转换行为；
  - 验证 `collect.main()`（mock `boards.collect`）产出的 `latest_run.json` 中 `run_at` 及条目 `published_at`、`collected_at` 全部严格以 `+08:00` 结尾。
- **`tests/test_worker_pulse.py`**：
  - 新增 `test_beijing_timezone_everywhere`：
    - 通过 `/api/ingest` 写入混合 `Z` 与 `-05:00` 时间的两条同事件新闻 + 一条较早新闻 + 手动插入一条历史 `+00:00` 报告行与新报告行；
    - 验证 `GET /api/news` 返回的所有 `published_at`、`collected_at`、`created_at` 及 `related_sources[].published_at` 全部以 `+08:00` 结尾，且按时间严格倒序；
    - 验证 `GET /api/reports` 按真实时间 `julianday` 倒序返回（无字符串跨时区倒挂），且 `run_at`、`created_at` 全部为 `+08:00`；
    - 验证 `GET /api/pulse`（含刷新与缓存命中）返回的 `updated_at` 全部以 `+08:00` 结尾。
  - 确保已有全部测试（含 `test_inline_script_vm_gate`、`test_api_news_filters_sports`、`test_api_news_clusters_same_event`）继续全绿。

---

## 3. Scope Out（排除范围）

- 不修改数据库表结构（不新增 migration 文件）；
- 不更改 `boards.py` 现有媒体源配置或引入付费 API；
- 不执行 `git push`、`gh pr create`、`wrangler deploy`。

---

## 4. Allowed Paths

- `collector/collect.py`
- `collector/boards.py`
- `collector/hackernews.py`
- `worker/src/index.js`
- `tests/test_collector.py`
- `tests/test_worker_pulse.py`

---

## 5. Acceptance Criteria

- **AC1**：`collector/collect.py`、`boards.py`、`hackernews.py` 产出的 `run_at`、`published_at`、`collected_at` 全部统一为 `YYYY-MM-DDTHH:MM:SS+08:00`（无 UTC `+00:00`/`Z` 残留），且 `to_beijing_iso` 对各种合法/非法输入处理正确。
- **AC2**：`worker/src/index.js` 的 `POST /api/ingest`、`GET /api/reports`、`GET /api/news`（含 `related_sources` 与 `created_at`）、`GET /api/pulse` 对历史 UTC/SQLite naive 时间与新时间均统一转换输出 `+08:00`，`/api/reports` 按 `julianday` 倒序、`/api/news` 聚类后严格按主条目时间倒序。
- **AC3**：`node --check worker/src/index.js` 与 `test_inline_script_vm_gate`（有/无 Token 双分支 `vm.Script`）全部通过。
- **AC4**：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 全部 `OK`（退出码 `0`）。

---

## 6. Deliverables & Test Commands

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

完成后在当前 AO worktree 本地 `git commit`，并通过 `/Users/fanjie/.local/bin/ao report --done` 上报（携带 `task_id: TASK-005`、`contract_version: 1`、`attempt: 1`、`result_sha`、测试退出码、`REVIEW_REQUIRED`），随后结束回合。
