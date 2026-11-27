# TASK-005 独立验收报告

- **task_id**: `TASK-005`
- **contract_version**: `1`
- **developer**: Cursor（AO session `global-news-monitor-5`, model `composer-2.5`）
- **acceptor**: Antigravity（独立代码审查 + 独立测试与跨时区排序对抗复测）
- **base_commit**: `9bb8c4dc212e85b81e2c521f41a035e3e0ed8224`（父主线 `main` 基线：`8f746188c4bc59965f03c609030382746f7893ed`）
- **accepted_attempt**: `1`
- **accepted_head_sha**: `88496e9dae3f02da3653c949478ddc25f5b03345`
- **verdict**: `passed`
- **验收时间**: `2026-11-27T07:35:25Z`

## 验收明细（AC1–AC4）

- **AC1**：`passed` — `collector/collect.py` 新增 `to_beijing_iso()`，将 `report["run_at"]` 及所有条目 `published_at`、`collected_at` 统一转为 `YYYY-MM-DDTHH:MM:SS+08:00` 并按真实时间戳倒序排序；`boards.py` 与 `hackernews.py` 同步使用 `timespec="seconds"` 的 `+08:00` 格式。
- **AC2**：`passed` — `worker/src/index.js` 实现确定性 `toBeijingIso()` / `formatBeijingMs()` / `normalizeNewsTimes()`，覆盖 `POST /api/ingest`、`GET /api/reports`（`ORDER BY julianday(run_at) DESC LIMIT 200` 且含 `created_at` 转换）、`GET /api/news`（含 `created_at`、`related_sources[].published_at` 与聚类后按主条目时间倒序）及 `GET /api/pulse`（`updated_at`）；独立对抗复测验证混合 `+00:00`、`-05:00` 与 SQLite naive `YYYY-MM-DD HH:MM:SS` 全部输出 `+08:00` 且排序无倒挂。
- **AC3**：`passed` — `node --check worker/src/index.js`（exit `0`）与 `test_inline_script_vm_gate`（有/无 Token 双分支 `vm.Script`）全部通过。
- **AC4**：`passed` — `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 共 59 项离线单测全部 `OK`（真实退出码 `0`）；改动文件严格位于 `Allowed Paths` 内。
