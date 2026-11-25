# DECISIONS

| 日期 | 决定 | 理由 | 链接 |
|---|---|---|---|
| 2026-11-25 | 本项目接入 AI 研发协作标准 V0.3：Antigravity 负责规划与独立验收，AO + Cursor（`composer-2.5`）负责隔离 worktree 研发 | 遵循全局默认研发协作标准，保障规划/开发/独立验收职责分离与等待零模型推理消耗 | `AGENTS.md` |
| 2026-11-25 | 不直接把 `last30days-skill` 整包塞入定时采集，而是拆解复用其免 Key 子模块思路（HN Algolia API + Polymarket Gamma API + Reddit 公开 JSON） | 整包为 Topic 驱动且部分源依赖登录态/付费 API；免 Key 公开接口零成本、确定性高，契合 GitHub Actions 8 分钟时限与 Cloudflare Worker 架构 | `docs/ai/tasks/TASK-001-hn-polymarket-community.md` |
| 2026-11-25 | 采用「采集期预关联入库 + Worker `/api/pulse` 按需查询带 D1 缓存」双通道承载社区与市场脉络 | 主列表首屏即可直接渲染 HN 热榜与 Polymarket 概率胶囊标签；用户点击任意新闻展开脉络时亦可实时补齐讨论且受缓存与失败隔离保护 | `docs/ai/tasks/TASK-001-hn-polymarket-community.md` |
| 2026-11-25 | 所有建设与集成仅在隔离分支 `collab/hn-polymarket-community` 进行，不触碰 `main` 与线上部署 | 遵守不擅自 push、不合并主线、不部署生产环境的红线 | `docs/ai/STATUS.md` |
| 2026-11-25 | 纯中文新闻源通过免密钥中译英缓存生成英文检索词（`en_title`），采集期社区预检索限制前 12 条并加超时取消兜底 | 解决中文标题无法直接命中英文 Polymarket 盘口与英文 HN/Reddit 讨论的问题，同时防止 GitHub Actions 并发限流或超时阻塞 | `docs/ai/reviews/TASK-001-acceptance.md` |
