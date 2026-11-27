# TASK-004 独立验收报告

- **task_id**: `TASK-004`
- **contract_version**: `1`
- **developer**: Cursor（AO session `global-news-monitor-4`, model `composer-2.5`）
- **acceptor**: Antigravity（独立代码审查 + 独立测试与对抗反例复测）
- **base_commit**: `73c251f9c26f9cf4760a8a3e4d793b25a3492329`（父主线 `main` 基线：`8aab1d17df8bffc16ffaeca662ee8bc3f0288f01`）
- **accepted_attempt**: `1`
- **accepted_head_sha**: `1232253d95db59cc2dec05560cbb371ff40c771e`
- **verdict**: `passed`
- **验收时间**: `2026-11-27T06:20:10Z`

## 验收明细（AC1–AC4）

- **AC1**：`passed` — `collector/events.py` 扩展同义词表（丧生/死亡、风暴/大风暴、导致/带来/造成、袭击/无人机袭击等）、中文虚词过滤与冲突主体保护；对抗实测「感恩节大风暴洪水/延误 vs 洪水/停电」及「两名意大利人科威特袭击丧生/伊朗否认」3 篇报道全部判定为同一事件，而「OpenAI vs Anthropic」「美联储 vs 欧洲央行」「法国 vs 意大利学校炸弹威胁」全部保持不合并。
- **AC2**：`passed` — `worker/src/index.js` 的 `GET /api/news` 接入并查集确定性聚类 `clusterNewsItems`，正确选出正文更完整的主条目、生成 `source_count` 与 `related_sources`、继承补齐 `image_url`/`polymarket` 并去重合并 `community`。
- **AC3**：`passed` — 前端 `PAGE` 渲染多源标识与 `<details class="related-sources">` 同题报道折叠列表，全量走 `esc()` 与 `safeHref()`；`node --check` 与独立 `vm.Script`（有/无 Token 双分支）均通过。
- **AC4**：`passed` — `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 共 50 项离线单测全部 `OK`（真实退出码 `0`）；改动严格限定在 `Allowed Paths` 内。
