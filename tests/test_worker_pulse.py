"""AC4/AC5/AC6：Worker 接口与前端逻辑离线验证。"""
import sqlite3
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker" / "src" / "index.js"
MIGRATIONS = ROOT / "migrations"

RUNTIME_SCRIPT = """
import { pathToFileURL } from 'url';
import { readFileSync } from 'fs';

const ROOT = process.argv[2];
const { DatabaseSync } = await import('node:sqlite');
const raw = new DatabaseSync(':memory:');
raw.exec(readFileSync(ROOT + '/migrations/0001_init.sql', 'utf8'));
raw.exec(readFileSync(ROOT + '/migrations/0002_context.sql', 'utf8'));

class Stmt {
  constructor(db, sql){ this.db = db; this.sql = sql; this.bound = []; }
  bind(...a){ this.bound = a; return this; }
  run(){
    if (this.sql.startsWith('CREATE TABLE')) this.db.exec(this.sql);
    else this.db.prepare(this.sql).run(...this.bound);
    return { meta: { changes: 1 } };
  }
  all(){ return { results: this.db.prepare(this.sql).all(...this.bound) }; }
  first(){ return this.db.prepare(this.sql).get(...this.bound) || null; }
}

class MemDB {
  constructor(db){ this.db = db; }
  prepare(sql){ return new Stmt(this.db, sql); }
  async batch(stmts){
    const results = [];
    for (const s of stmts) {
      s.run();
      const ch = this.db.prepare('SELECT changes() AS c').get();
      results.push({ results: [{ new_count: ch?.c ?? 0 }] });
    }
    return results;
  }
  async run(stmt){ return stmt.run(); }
  async all(stmt){ return stmt.all(); }
  async first(stmt){ return stmt.first(); }
}

const mod = await import(pathToFileURL(ROOT + '/worker/src/index.js').href);
const handler = mod.default;
const env = { DB: new MemDB(raw), INGEST_TOKEN: 'test-token' };
const fp = 'a'.repeat(64);
const fp2 = 'b'.repeat(64);
const fp3 = 'c'.repeat(64);
const gammaEvents = [{
  slug: 'trump-2028-election',
  title: 'Donald Trump wins 2028 presidential election',
  volume: 1000000,
  markets: [{
    question: 'Will Donald Trump win the 2028 presidential election?',
    outcomes: '["Yes","No"]',
    outcomePrices: '["0.42","0.58"]',
    closed: false
  }]
}];

const ingest = await handler.fetch(new Request('http://x/api/ingest', { method: 'POST', headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify({
  run_at: '2026-01-01T08:00:00+08:00', candidate_count: 2, source_error_count: 0, source_errors: [], ranked: true,
  items: [
    { fingerprint: fp, source_name: '路透社', category: '国际政治', title: '测试', url: 'https://example.com/n', collected_at: '2026-01-01T08:00:00+08:00',
      polymarket: { event_title: '盘', question: 'Q', outcome: 'Yes', probability: 60, volume_text: '$1M', url: 'https://polymarket.com/event/x' },
      community: { hn: [{ title: 'HN', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=1' }] },
      query_terms: ['test', 'news'] },
    { fingerprint: fp2, source_name: '路透社', category: '国际政治', title: '特朗普2028竞选', url: 'https://example.com/m', collected_at: '2026-01-01T08:00:00+08:00',
      query_terms: ['donald', 'trump', 'campaign', 'rally'] },
    { fingerprint: fp3, source_name: '路透社', category: '国际政治', title: '无关新闻', url: 'https://example.com/z', collected_at: '2026-01-01T08:00:00+08:00',
      query_terms: ['zzxxyy', 'qqwwrr'] }
  ]
}) }), env);
if (!(await ingest.json()).ok) throw new Error('ingest');

const news = await handler.fetch(new Request('http://x/api/news?date=2026-01-01'), env);
if (!(await news.json()).items?.[0]?.polymarket) throw new Error('news join');

let r = await handler.fetch(new Request('http://x/api/pulse?fingerprint=bad'), env);
if (r.status !== 400) throw new Error('400');
r = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + 'd'.repeat(64)), env);
if (r.status !== 404) throw new Error('404');

const realFetch = globalThis.fetch;
globalThis.fetch = async (url, opts) => {
  const u = String(url);
  if (u.includes('gamma-api.polymarket.com')) return new Response(JSON.stringify(gammaEvents), { status: 200 });
  if (u.includes('hn.algolia')) return new Response(JSON.stringify({ hits: [{ objectID: '2', title: 'HN', points: 3, num_comments: 1 }] }));
  if (u.includes('reddit.com')) return new Response(JSON.stringify({ data: { children: [{ data: { subreddit: 'news', title: 'R', score: 1, num_comments: 1, permalink: '/r/news/x' } }] } }));
  return realFetch(url, opts);
};

const pulsePm = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp2 + '&refresh=1'), env);
const pmJson = await pulsePm.json();
if (!pmJson.ok || !pmJson.polymarket || pmJson.source_status.polymarket !== 'ok') throw new Error('polymarket match');
if (pmJson.community.hn_meta !== undefined) throw new Error('hn_meta leaked');

globalThis.fetch = async (url) => {
  if (String(url).includes('gamma-api.polymarket.com')) return new Response(JSON.stringify([]), { status: 200 });
  if (String(url).includes('hn.algolia')) return new Response(JSON.stringify({ hits: [] }));
  if (String(url).includes('reddit.com')) return new Response(JSON.stringify({ data: { children: [] } }));
  return realFetch(url);
};
const pulseEmpty = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp3 + '&refresh=1'), env);
const emptyJson = await pulseEmpty.json();
if (emptyJson.source_status.polymarket !== 'empty') throw new Error('expected polymarket empty');

const pulse = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp + '&refresh=1'), env);
if ((await pulse.json()).cached !== false) throw new Error('pulse refresh');

raw.prepare('UPDATE news_context SET updated_at = ?, community_json = ? WHERE fingerprint = ?').run(
  new Date().toISOString(),
  JSON.stringify({ hn_meta: { points: 9 }, hn: [{ title: 'c', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=3' }], reddit: [] }),
  fp
);
const cached = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp), env);
const cacheJson = await cached.json();
if (!cacheJson.cached || cacheJson.community.hn_meta !== undefined) throw new Error('cache clean community');

const page = await handler.fetch(new Request('http://x/'), env);
const html = await page.text();
for (const n of ['社区与市场脉络', 'pmcap', '/api/pulse', '讨论摘录']) if (!html.includes(n)) throw new Error('page ' + n);
console.log('OK');
"""


class WorkerPulseTests(unittest.TestCase):
    def test_node_syntax(self):
        r = subprocess.run(["node", "--check", str(WORKER)], capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_migrations_chain(self):
        db = sqlite3.connect(":memory:")
        db.executescript((MIGRATIONS / "0001_init.sql").read_text())
        db.executescript((MIGRATIONS / "0002_context.sql").read_text())
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("news_context", tables)

    def test_worker_runtime(self):
        script = ROOT / "tests" / "_worker_runtime.mjs"
        script.write_text(RUNTIME_SCRIPT, encoding="utf-8")
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()