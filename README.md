# Global News Monitor

Cloud-hosted, public, Chinese-language global news monitoring. V1 is designed around GitHub Actions (30-minute collection), Cloudflare D1 (history), and Cloudflare Workers (public web/API).

## Status

Initial repository scaffold. **Not yet deployed and not yet operational.** RSS source reliability, event-level deduplication, source verification, Chinese summaries, alerting, and production UI must pass tests before calling V1 complete.

## Architecture

- `collector/`: Python RSS ingestion and normalization; runs in GitHub Actions.
- `migrations/`: Cloudflare D1 schema.
- `worker/`: public read-only news center and API.
- `.github/workflows/`: scheduled collection workflow.

## Local collector check

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The collector requires `NEWS_DATABASE_URL` only when using a remote persistence adapter. The initial workflow intentionally does not pretend to persist data until D1 ingestion credentials and an authenticated ingestion endpoint are configured.

## Cloudflare deployment (pending)

1. Create a D1 database named `global-news-db`.
2. Apply `migrations/0001_init.sql`.
3. Create a Worker from `worker/`, bind D1 as `DB`, and deploy.
4. Configure GitHub repository secrets for the ingestion endpoint/token and Cloudflare deployment as documented in the deployment guide (to be added after the first live smoke test).

## Operating guarantees to validate

- A report is created every scheduled run, including an explicit "本轮无重大新增" report.
- Candidate RSS items are not described as verified major news.
- Duplicate items are suppressed by canonical URL/hash.
- Run errors and source-level failures are visible.
- The schedule is best-effort; GitHub Actions can start late.
