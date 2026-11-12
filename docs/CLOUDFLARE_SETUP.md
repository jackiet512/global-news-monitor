# Cloudflare deployment

1. Cloudflare Dashboard → Workers & Pages → D1 SQL Database → Create database. Name it `global-news-db`, then copy its database ID.
2. Replace the placeholder database_id in `worker/wrangler.toml`.
3. From the repository root:
   ```bash
   cd worker
   npm install
   npx wrangler d1 execute global-news-db --remote --file=../migrations/0001_init.sql
   npx wrangler secret put INGEST_TOKEN
   npm run deploy
   ```
4. Generate a long random token locally. Enter it for the Worker secret and also add GitHub repository secrets:
   - `NEWS_INGEST_TOKEN`: same random token
   - `NEWS_INGEST_URL`: `https://YOUR-WORKER-DOMAIN/api/ingest`

Never commit tokens. Check `/api/health`, then run the GitHub Actions workflow manually. D1 persistence only works after deployment and both GitHub secrets are configured. GitHub scheduled starts are best-effort and may be delayed.
