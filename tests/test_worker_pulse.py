"""AC4/AC5/AC6：Worker 接口与前端逻辑离线验证。"""
import json
import sqlite3
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "worker" / "src" / "index.js"
MIGRATIONS = ROOT / "migrations"

NODE_TEST = r"""
import { createRequire } from 'module';
import { pathToFileURL } from 'url';
import { readFileSync } from 'fs';

const ROOT = process.argv[2];
const workerPath = ROOT + '/worker/src/index.js';
const mod = await import(pathToFileURL(workerPath).href);
const handler = mod.default;

class Stmt {
  constructor(sql){this.sql=sql;this.bound=[]}
  bind(...args){this.bound=args;return this}
}

class MemDB {
  constructor(db){this.db=db}
  prepare(sql){return new Stmt(sql)}
  async batch(stmts){
    const results=[];
    for(const s of stmts){
      if(s.sql.startsWith('CREATE TABLE')) this.db.exec(s.sql);
      else if(s.sql.includes('INSERT')||s.sql.includes('UPDATE')||s.sql.includes('REPLACE')||s.sql.includes('DELETE')){
        this.db.prepare(s.sql.replace(/RETURNING.*/,'')).run(...s.bound);
        results.push({results:[{new_count:this.db.prepare('SELECT changes() c').get().c}]});
      }
    }
    return results;
  }
  async run(){
    const sql=arguments[0].sql||arguments[0];
    const args=arguments[0].bound||[];
    if(typeof sql==='string'&&sql.startsWith('CREATE')) this.db.exec(sql);
    else if(arguments[0] instanceof Stmt) this.db.prepare(arguments[0].sql).run(...arguments[0].bound);
    return {meta:{changes:1}};
  }
  async all(){const s=arguments[0];const rows=this.db.prepare(s.sql).all(...s.bound);return {results:rows}}
  async first(){const s=arguments[0];return this.db.prepare(s.sql).get(...s.bound)||null}
  exec(sql){this.db.exec(sql)}
}

function initDb(){
  const db=new (createRequire(import.meta.url)('node:module'),).createRequire ? null : null;
}

const Database = (await import('node:sqlite')).Database || null;
let sqliteDb;
try{
  const { Database: D1 } = await import('node:sqlite');
  sqliteDb = new D1(':memory:');
}catch{
  const { default: initSqlJs } = await import('sql.js');
  const SQL = await initSqlJs();
  sqliteDb = SQL;
}

// Fallback: use better-sqlite3 via child or built-in sqlite in Node 22+
const { Database: Sqlite3 } = await import('node:sqlite');
const raw = new Sqlite3(':memory:');
const sql1 = readFileSync(ROOT+'/migrations/0001_init.sql','utf8');
const sql2 = readFileSync(ROOT+'/migrations/0002_context.sql','utf8');
raw.exec(sql1);
raw.exec(sql2);

const env={DB:new MemDB(raw),INGEST_TOKEN:'test-token',GITHUB_ACTIONS_TOKEN:''};

const fp='a'.repeat(64);
const ingestBody={
 run_at:'2026-01-01T08:00:00+08:00',
 candidate_count:1,
 source_error_count:0,
 source_errors:[],
 ranked:true,
 items:[{
  fingerprint:fp,
  source_name:'路透社',
  category:'国际政治',
  title:'测试新闻',
  url:'https://example.com/news',
  summary:'摘要',
  collected_at:'2026-01-01T08:00:00+08:00',
  polymarket:{event_title:'测试盘口',question:'Q',outcome:'Yes',probability:55,volume_text:'$1M',url:'https://polymarket.com/event/x'},
  community:{hn:[{title:'HN帖',points:10,num_comments:2,discussion_url:'https://news.ycombinator.com/item?id=1'}],reddit:[]},
  query_terms:['test','news']
 }]
};
const ingestReq=new Request('http://localhost/api/ingest',{method:'POST',headers:{Authorization:'Bearer test-token','Content-Type':'application/json'},body:JSON.stringify(ingestBody)});
const ingestRes=await handler.fetch(ingestReq,env);
const ingestJson=await ingestRes.json();
if(!ingestJson.ok) throw new Error('ingest failed '+JSON.stringify(ingestJson));

const newsReq=new Request('http://localhost/api/news?date=2026-01-01');
const newsRes=await handler.fetch(newsReq,env);
const newsJson=await newsRes.json();
if(!newsJson.items?.[0]?.polymarket) throw new Error('news missing polymarket');

const badPulse=await handler.fetch(new Request('http://localhost/api/pulse?fingerprint=bad'),env);
if(badPulse.status!==400) throw new Error('expected 400 invalid fingerprint');

const missPulse=await handler.fetch(new Request('http://localhost/api/pulse?fingerprint='+('b'.repeat(64))),env);
if(missPulse.status!==404) throw new Error('expected 404 not_found');

const realFetch=globalThis.fetch;
globalThis.fetch=async(url,opts)=>{
 if(String(url).includes('hn.algolia')) return new Response(JSON.stringify({hits:[{objectID:'2',title:'Fetched HN',points:5,num_comments:1}]}));
 if(String(url).includes('reddit.com')) return new Response(JSON.stringify({data:{children:[{data:{subreddit:'news',title:'Fetched',score:9,num_comments:1,permalink:'/r/news/x'}}]}}));
 return realFetch(url,opts);
};
const pulseRes=await handler.fetch(new Request('http://localhost/api/pulse?fingerprint='+fp+'&refresh=1'),env);
const pulseJson=await pulseRes.json();
if(!pulseJson.ok||pulseJson.cached!==false) throw new Error('pulse refresh failed');

raw.prepare("UPDATE news_context SET updated_at=?, community_json=? WHERE fingerprint=?").run(
 new Date().toISOString(),
 JSON.stringify({hn:[{title:'cached',points:1,num_comments:1,discussion_url:'https://news.ycombinator.com/item?id=3'}],reddit:[]}),
 fp
);
const cacheRes=await handler.fetch(new Request('http://localhost/api/pulse?fingerprint='+fp),env);
const cacheJson=await cacheRes.json();
if(!cacheJson.cached) throw new Error('expected cached true');

const pageReq=new Request('http://localhost/');
const pageRes=await handler.fetch(pageReq,env);
const html=await pageRes.text();
for(const needle of ['社区与市场脉络','pmcap','/api/pulse','esc(']){
 if(!html.includes(needle)) throw new Error('page missing '+needle);
}
console.log('WORKER_TESTS_OK');
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
        script.write_text(
            """
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
const body = {
  run_at: '2026-01-01T08:00:00+08:00', candidate_count: 1, source_error_count: 0,
  source_errors: [], ranked: true,
  items: [{
    fingerprint: fp, source_name: '路透社', category: '国际政治', title: '测试',
    url: 'https://example.com/n', collected_at: '2026-01-01T08:00:00+08:00',
    polymarket: { event_title: '盘', question: 'Q', outcome: 'Yes', probability: 60, volume_text: '$1M', url: 'https://polymarket.com/event/x' },
    community: { hn: [{ title: 'HN', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=1' }] },
    query_terms: ['test', 'news']
  }]
};
const ingest = await handler.fetch(new Request('http://x/api/ingest', { method: 'POST', headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify(body) }), env);
if (!(await ingest.json()).ok) throw new Error('ingest');

const news = await handler.fetch(new Request('http://x/api/news?date=2026-01-01'), env);
const newsJson = await news.json();
if (!newsJson.items?.[0]?.polymarket) throw new Error('news join');

let r = await handler.fetch(new Request('http://x/api/pulse?fingerprint=bad'), env);
if (r.status !== 400) throw new Error('400');
r = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + 'b'.repeat(64)), env);
if (r.status !== 404) throw new Error('404');

const realFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  if (String(url).includes('hn.algolia')) return new Response(JSON.stringify({ hits: [{ objectID: '2', title: 'HN', points: 3, num_comments: 1 }] }));
  if (String(url).includes('reddit.com')) return new Response(JSON.stringify({ data: { children: [{ data: { subreddit: 'news', title: 'R', score: 1, num_comments: 1, permalink: '/r/news/x' } }] } }));
  return realFetch(url);
};
const pulse = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp + '&refresh=1'), env);
const pj = await pulse.json();
if (!pj.ok || pj.cached !== false) throw new Error('pulse');

raw.prepare('UPDATE news_context SET updated_at = ?, community_json = ? WHERE fingerprint = ?').run(
  new Date().toISOString(),
  JSON.stringify({ hn: [{ title: 'c', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=3' }], reddit: [] }),
  fp
);
const cached = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fp), env);
if (!(await cached.json()).cached) throw new Error('cache');

const page = await handler.fetch(new Request('http://x/'), env);
const html = await page.text();
for (const n of ['社区与市场脉络', 'pmcap', '/api/pulse', 'esc(']) if (!html.includes(n)) throw new Error('page ' + n);
console.log('OK');
""",
            encoding="utf-8",
        )
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()