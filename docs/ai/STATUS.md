# STATUS

更新时间：2026-11-25
当前阶段：`TASK-001` 合同就绪并准备派发（隔离建设分支 `collab/hn-polymarket-community`，主线基线 `c1e7f4a5a8dd86a79465762972087b05c7930849`）
进行中任务：`docs/ai/tasks/TASK-001-hn-polymarket-community.md`（主列表接入 HN 热榜与 Polymarket 概率标签 + 单条新闻展开社区讨论脉络）
最近验收：尚无（首次接入 AI 研发协作标准）
已知问题：
1. 仓库内历史遗留 `collector/sources.json` 当前未被 `collector/collect.py` 实际消费（实际生效信源为 `collector/boards.py` 的 `SITES`）。
2. 工作区根目录存在未跟踪系统文件 `.DS_Store`，已保留现场不入库。
下一步：
1. 注册 AO 项目 `global-news-monitor`（worker=cursor，模型 `composer-2.5`）。
2. 基于隔离分支 `collab/hn-polymarket-community` 派发 `TASK-001` 给 Cursor worker，并启动非模型监听脚本 `watch_ao_worker.py` 等待交付后独立验收。
