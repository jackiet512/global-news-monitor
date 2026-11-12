# 部署说明

在 Cloudflare 创建 D1 数据库，将数据库标识填入 `worker/wrangler.toml`，绑定名称为 `DB`。在仓库目录执行：

```sh
cd worker
npm install
npx wrangler d1 execute global-news-db --remote --file=../migrations/0001_init.sql
npm run deploy
npx wrangler secret put INGEST_TOKEN
```

在 GitHub 仓库的 Actions 密钥设置中保存写入接口地址 `NEWS_INGEST_URL` 和令牌 `NEWS_INGEST_TOKEN`。令牌须与生产环境的 `INGEST_TOKEN` 相同。仅在密钥输入界面填写令牌。

手动运行采集工作流，查看写入结果，并通过 `/api/news` 和 `/api/reports` 核对新闻和报告。
