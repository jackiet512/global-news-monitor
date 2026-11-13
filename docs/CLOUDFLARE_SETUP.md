# 部署说明

在 Cloudflare 创建 D1 数据库，将数据库标识填入 `worker/wrangler.toml`，绑定名称为 `DB`。在仓库目录执行：

```sh
cd worker
npm install
npx wrangler d1 execute global-news-db --remote --file=../migrations/0001_init.sql
npm run deploy
npx wrangler secret put INGEST_TOKEN
npx wrangler secret put GITHUB_ACTIONS_TOKEN
```

在 GitHub 仓库的 Actions 密钥设置中保存写入接口地址 `NEWS_INGEST_URL` 和令牌 `NEWS_INGEST_TOKEN`。令牌须与生产环境的 `INGEST_TOKEN` 相同。仅在密钥输入界面填写令牌。

手动运行采集工作流，查看写入结果，并通过 `/api/news` 和 `/api/reports` 核对新闻和报告。


## 双重定时保障

GitHub Actions 保留原有每小时第 7、37 分钟的定时采集。Cloudflare Worker 另设每小时第 20、50 分钟的备用检查：读取 GitHub Actions 最近运行记录；若最近一次运行已超过 45 分钟，则调用 GitHub workflow_dispatch 触发采集。若 GitHub 最近有运行（包括排队或执行中），备用调度不会重复触发。

首次启用前，在 GitHub 创建一个仅授权此仓库的 Fine-grained personal access token，Repository permissions 至少设置 **Actions: Read and write**。在 Worker 目录执行 `npx wrangler secret put GITHUB_ACTIONS_TOKEN`，粘贴该令牌。不要把令牌提交到 Git 仓库或写进 wrangler.toml。然后执行 `npm run deploy` 发布 Worker；Cloudflare Cron Trigger 会随配置部署生效。可在 Cloudflare Worker 的 Logs 中查看 `schedule-fallback` 记录。
