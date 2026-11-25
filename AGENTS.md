# AGENTS.md

一句话目标：全球新闻中心（`global-news-monitor`）——零付费 API、纯确定性规则驱动的多源全球要闻与科技/预测市场/社区脉络聚合站点。

## 先读

1. `docs/ai/PROJECT.md` — 目标、范围、架构、关键目录、运行与测试、限制
2. `docs/ai/STATUS.md` — 当前阶段、进行中任务、最近验收、已知问题、下一步
3. `docs/ai/DECISIONS.md` — 决策记录
4. 当前任务合同（`docs/ai/tasks/` 或对应 Issue / PR）

## 角色绑定（遵循 AI 研发协作标准 V0.3）

| 角色 | 绑定工具 | 职责与结束条件 |
|---|---|---|
| planner / acceptor | Antigravity | 编写任务合同、经 AO 派发、非模型监听唤醒后独立验收（读完整 diff + 独立复跑测试与反例），更新状态快照 |
| developer | Cursor（经 AO worker，默认 composer-2.5） | 隔离 worktree 内完成研发、测试、自查、本地 commit，`ao report --done` 携带合同版本与交付 SHA 后结束回合 |

## 规则

- 开发者交付后停止扩展任务，等待独立验收意见。
- 验收者不得直接修改业务代码后自行宣布验收通过。
- 更换工具或模型只改配置并经负责人确认，禁止静默换模型。
- 严禁启用任何付费 API、购买套餐、提交密钥。
- **本项目发布授权（2026-11-25 负责人书面确认）**：本仓库任务在完成独立验收（`status:accepted`）后，自动合并至 `main` 并 `git push origin main` 同步发布到 GitHub；若涉及 Cloudflare D1 迁移或 `wrangler deploy` 且需要同步上线，一并记录部署证据。
