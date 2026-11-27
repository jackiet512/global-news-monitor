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

SPORTS_FILTER_SCRIPT = """
import { pathToFileURL } from 'url';
import { readFileSync } from 'fs';

const ROOT = process.argv[2];
const { DatabaseSync } = await import('node:sqlite');
const raw = new DatabaseSync(':memory:');
raw.exec(readFileSync(ROOT + '/migrations/0001_init.sql', 'utf8'));

class Stmt {
  constructor(db, sql){ this.db = db; this.sql = sql; this.bound = []; }
  bind(...a){ this.bound = a; return this; }
  run(){ this.db.prepare(this.sql).run(...this.bound); return { meta: { changes: 1 } }; }
  all(){ return { results: this.db.prepare(this.sql).all(...this.bound) }; }
  first(){ return this.db.prepare(this.sql).get(...this.bound) || null; }
}

class MemDB {
  constructor(db){ this.db = db; }
  prepare(sql){ return new Stmt(this.db, sql); }
  async batch(stmts){ for (const s of stmts) s.run(); return []; }
  async run(stmt){ return stmt.run(); }
  async all(stmt){ return stmt.all(); }
  async first(stmt){ return stmt.first(); }
}

const mod = await import(pathToFileURL(ROOT + '/worker/src/index.js').href);
const handler = mod.default;
const env = { DB: new MemDB(raw) };

const fpPol = 'd'.repeat(64);
const fpSport = 'e'.repeat(64);
raw.prepare('INSERT INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)').run(
  fpPol, '路透社', '国际政治', '联合国安理会讨论中东局势', 'https://reuters.com/world/mideast', '', '2026-01-01T10:00:00+08:00', '2026-01-01T10:00:00+08:00', '待核实'
);
raw.prepare('INSERT INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)').run(
  fpSport, '英国广播公司', '社会与突发', '英超争冠最新积分榜', 'https://www.bbc.com/sport/football/table', '', '2026-01-01T09:00:00+08:00', '2026-01-01T09:00:00+08:00', '待核实'
);

const news = await handler.fetch(new Request('http://x/api/news?date=2026-01-01'), env);
const data = await news.json();
if (!data.items || data.items.length !== 1) throw new Error('expected 1 item after sports filter, got ' + (data.items?.length ?? 0));
if (data.items[0].fingerprint !== fpPol) throw new Error('wrong item returned');
if (data.items.some(x => x.fingerprint === fpSport)) throw new Error('sports item not filtered');

const fpEmerg = 'f'.repeat(64);
raw.prepare('INSERT INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)').run(
  fpEmerg, '路透社', '社会与突发', '足球场踩踏事件致多人伤亡', 'https://reuters.com/world/stadium-stampede', '', '2026-01-01T11:00:00+08:00', '2026-01-01T11:00:00+08:00', '待核实'
);
const news2 = await handler.fetch(new Request('http://x/api/news?date=2026-01-01'), env);
const data2 = await news2.json();
if (!data2.items.some(x => x.fingerprint === fpEmerg)) throw new Error('emergency exempt item filtered');

console.log('OK');
"""

INLINE_SCRIPT_GATE = """
import { pathToFileURL } from 'url';
import vm from 'vm';

const ROOT = process.argv[2];
const mod = await import(pathToFileURL(ROOT + '/worker/src/index.js').href);
const handler = mod.default;

function extractScript(html) {
  const m = html.match(/<script>([\\s\\S]*?)<\\/script>/);
  if (!m) throw new Error('no inline script');
  return m[1];
}

function assertParses(code, label) {
  try {
    new vm.Script(code);
  } catch (e) {
    throw new Error(label + ': ' + e.message);
  }
}

const memEnv = { DB: null };

const withTok = { ...memEnv, GITHUB_ACTIONS_TOKEN: 'tok' };
const htmlTok = await (await handler.fetch(new Request('http://x/'), withTok)).text();
const codeTok = extractScript(htmlTok);
assertParses(codeTok, 'with token');

const noTok = { ...memEnv, GITHUB_ACTIONS_TOKEN: '' };
const htmlNo = await (await handler.fetch(new Request('http://x/'), noTok)).text();
const codeNo = extractScript(htmlNo);
assertParses(codeNo, 'without token');

function fnBlock(code) {
  const start = code.indexOf('function esc');
  const end = code.indexOf('const pulseInflight');
  if (start < 0 || end < 0) throw new Error('cannot isolate front-end helpers');
  return code.slice(start, end);
}

const ctx = {};
vm.createContext(ctx);
vm.runInContext(fnBlock(codeTok), ctx);

const hrefCases = [
  ['https://polymarket.com/event/x', 'https://polymarket.com/event/x'],
  ['http://example.com/a', 'http://example.com/a'],
  ['javascript:alert(1)', ''],
  ['https:evil', ''],
  ['', ''],
];
for (const [input, expected] of hrefCases) {
  const got = vm.runInContext('safeHref(' + JSON.stringify(input) + ')', ctx);
  if (got !== expected) throw new Error('safeHref(' + JSON.stringify(input) + ') => ' + JSON.stringify(got) + ', want ' + JSON.stringify(expected));
}

const pulse = vm.runInContext(
  "renderPulse({polymarket:{event_title:'<script>alert(1)</script>',outcome:'Yes',probability:50,url:'javascript:alert(1)'},community:{}})",
  ctx
);
if (pulse.includes('<script>alert(1)</script>')) throw new Error('renderPulse XSS: script tag not escaped');
if (pulse.includes('javascript:')) throw new Error('renderPulse XSS: javascript link leaked');
if (!pulse.includes('&lt;script&gt;')) throw new Error('renderPulse: expected escaped script in output');

console.log('OK');
"""

CLUSTER_SCRIPT = """
import { pathToFileURL } from 'url';
import vm from 'vm';
import { readFileSync } from 'fs';

const ROOT = process.argv[2];
const { DatabaseSync } = await import('node:sqlite');
const raw = new DatabaseSync(':memory:');
raw.exec(readFileSync(ROOT + '/migrations/0001_init.sql', 'utf8'));
raw.exec(readFileSync(ROOT + '/migrations/0002_context.sql', 'utf8'));

class Stmt {
  constructor(db, sql){ this.db = db; this.sql = sql; this.bound = []; }
  bind(...a){ this.bound = a; return this; }
  run(){ this.db.prepare(this.sql).run(...this.bound); return { meta: { changes: 1 } }; }
  all(){ return { results: this.db.prepare(this.sql).all(...this.bound) }; }
  first(){ return this.db.prepare(this.sql).get(...this.bound) || null; }
}

class MemDB {
  constructor(db){ this.db = db; }
  prepare(sql){ return new Stmt(this.db, sql); }
  async batch(stmts){ for (const s of stmts) s.run(); return []; }
  async run(stmt){ return stmt.run(); }
  async all(stmt){ return stmt.all(); }
  async first(stmt){ return stmt.first(); }
}

const mod = await import(pathToFileURL(ROOT + '/worker/src/index.js').href);
const handler = mod.default;
const env = { DB: new MemDB(raw) };
raw.exec('CREATE TABLE IF NOT EXISTS news_reading (fingerprint TEXT PRIMARY KEY,image_url TEXT,reading_text TEXT,short_body INTEGER)');
raw.exec('CREATE TABLE IF NOT EXISTS news_context (fingerprint TEXT PRIMARY KEY,polymarket_json TEXT,community_json TEXT,query_terms TEXT,updated_at TEXT NOT NULL)');

const day = '2026-11-25T10:00:00+08:00';
const items = [
  { fp: '1'.repeat(64), src: '路透社', title: '感恩节大风暴给美国带来洪水和航班延误', url: 'https://reuters.com/storm-a', cat: '社会与突发',
    pm: { event_title: 'Storm', question: 'Q', outcome: 'Yes', probability: 55, url: 'https://polymarket.com/event/storm' }, img: 'https://cdn.example.com/storm.jpg', body: 'Reuters longer body text about flooding and delays across the US.' },
  { fp: '2'.repeat(64), src: '美联社', title: '强大的感恩节风暴导致洪水、停电', url: 'https://apnews.com/storm-b', cat: '社会与突发', pm: null, img: '', body: 'Short AP note.' },
  { fp: '3'.repeat(64), src: '彭博社', title: '两名意大利人在科威特袭击中丧生，伊朗否认对此负责', url: 'https://bloomberg.com/kuwait-a', cat: '国际政治', pm: null, img: '', body: 'Bloomberg Kuwait attack lead.' },
  { fp: '4'.repeat(64), src: '路透社', title: '伊朗被指控在科威特发动无人机袭击，造成两名意大利人死亡', url: 'https://reuters.com/kuwait-b', cat: '国际政治', pm: null, img: 'https://cdn.example.com/kuwait.jpg', body: '' },
  { fp: '5'.repeat(64), src: '法新社', title: '两名意大利人在科威特袭击事件中丧生，伊朗否认参与', url: 'https://afp.com/kuwait-c', cat: '国际政治', pm: null, img: '', body: 'AFP duplicate angle.' },
  { fp: '6'.repeat(64), src: '华尔街日报', title: 'OpenAI发布新一代推理模型', url: 'https://wsj.com/openai', cat: 'AI与科技', pm: null, img: '', body: '' },
  { fp: '7'.repeat(64), src: '纽约时报', title: '美联储宣布维持利率不变', url: 'https://nytimes.com/fed', cat: '全球经济金融', pm: null, img: '', body: '' },
];

for (const x of items) {
  raw.prepare('INSERT INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)').run(
    x.fp, x.src, x.cat, x.title, x.url, x.body, day, day, '待核实'
  );
  if (x.img || x.body) raw.prepare('INSERT INTO news_reading (fingerprint,image_url,reading_text,short_body) VALUES (?,?,?,?)').run(x.fp, x.img || '', x.body || '', 0);
  if (x.pm) raw.prepare('INSERT INTO news_context (fingerprint,polymarket_json,community_json,query_terms,updated_at) VALUES (?,?,?,?,?)').run(
    x.fp, JSON.stringify(x.pm), JSON.stringify({ hn: [{ title: 'HN ' + x.src, points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=' + x.fp.slice(0,2) }], reddit: [] }), '[]', day
  );
}

const news = await handler.fetch(new Request('http://x/api/news?date=2026-11-25&limit=20'), env);
const data = await news.json();
if (!data.items || data.items.length !== 4) throw new Error('expected 4 clustered cards, got ' + (data.items?.length ?? 0));

const storm = data.items.find(x => x.title.includes('感恩节'));
const kuwait = data.items.find(x => x.title.includes('科威特') || x.title.includes('意大利'));
const openai = data.items.find(x => x.title.includes('OpenAI'));
const fed = data.items.find(x => x.title.includes('美联储'));
if (!storm || !kuwait || !openai || !fed) throw new Error('missing expected topic cards');

if (storm.source_count !== 2 || storm.related_sources?.length !== 1) throw new Error('storm cluster wrong: ' + JSON.stringify({ source_count: storm.source_count, rel: storm.related_sources?.length }));
if (!storm.polymarket || !storm.image_url) throw new Error('storm missing inherited polymarket/image_url');
if (storm.related_sources[0].source_name !== '美联社') throw new Error('storm related source wrong');

if (kuwait.source_count !== 3 || kuwait.related_sources?.length !== 2) throw new Error('kuwait cluster wrong');
if (!kuwait.image_url) throw new Error('kuwait missing inherited image_url');

if (openai.related_sources?.length || fed.related_sources?.length) throw new Error('unrelated items should not cluster');

const page = await handler.fetch(new Request('http://x/'), env);
const html = await page.text();
for (const n of ['related-sources', '同题报道', '多源报道']) if (!html.includes(n)) throw new Error('page missing ' + n);

const m = html.match(/<script>([\\s\\S]*?)<\\/script>/);
if (!m) throw new Error('no inline script');
new vm.Script(m[1]);

console.log('OK');
"""

BEIJING_TIMEZONE_SCRIPT = """
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

function endsBj(v){ return typeof v === 'string' && v.endsWith('+08:00'); }
function assertBj(v, label){ if (!endsBj(v)) throw new Error(label + ': ' + JSON.stringify(v)); }

const fpA = 'a'.repeat(64);
const fpB = 'b'.repeat(64);
const fpC = 'c'.repeat(64);
const fpD = 'd'.repeat(64);

const ingest = await handler.fetch(new Request('http://x/api/ingest', { method: 'POST', headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' }, body: JSON.stringify({
  run_at: '2026-01-15T02:00:00Z',
  candidate_count: 3, source_error_count: 0, source_errors: [], ranked: false,
  items: [
    { fingerprint: fpA, source_name: '路透社', category: '社会与突发', title: '感恩节大风暴给美国带来洪水和航班延误', url: 'https://reuters.com/storm-a', published_at: '2026-01-15T14:00:00Z', collected_at: '2026-01-15T14:00:00Z' },
    { fingerprint: fpB, source_name: '美联社', category: '社会与突发', title: '强大的感恩节风暴导致洪水、停电', url: 'https://apnews.com/storm-b', published_at: '2026-01-15T09:00:00-05:00', collected_at: '2026-01-15T09:00:00-05:00' },
    { fingerprint: fpC, source_name: '路透社', category: '国际政治', title: '美联储宣布维持利率不变', url: 'https://reuters.com/fed', published_at: '2026-01-14T08:00:00Z', collected_at: '2026-01-14T08:00:00Z' },
  ]
}) }), env);
if (!(await ingest.json()).ok) throw new Error('ingest failed');

raw.prepare('INSERT INTO reports (run_at,candidate_count,new_count,source_error_count,summary,created_at) VALUES (?,?,?,?,?,?)').run(
  '2026-01-15T02:00:00+00:00', 5, 3, 0, '旧报告', '2026-01-15T02:00:00+00:00'
);
raw.prepare('INSERT INTO reports (run_at,candidate_count,new_count,source_error_count,summary,created_at) VALUES (?,?,?,?,?,?)').run(
  '2026-01-15T22:00:00+08:00', 10, 8, 1, '新报告', '2026-01-15T22:00:00+08:00'
);

const reports = await handler.fetch(new Request('http://x/api/reports?date=2026-01-15'), env);
const repData = await reports.json();
if (repData.items.length < 2) throw new Error('expected multiple reports');
for (const row of repData.items) {
  assertBj(row.run_at, 'report.run_at');
  assertBj(row.created_at, 'report.created_at');
}
const newest = repData.items[0].run_at;
const oldest = repData.items[repData.items.length - 1].run_at;
if (Date.parse(newest) <= Date.parse(oldest)) throw new Error('reports not desc: ' + newest + ' vs ' + oldest);

const news = await handler.fetch(new Request('http://x/api/news?date=2026-01-15&limit=20'), env);
const newsData = await news.json();
if (!newsData.items?.length) throw new Error('no news items');

function checkNewsItem(item){
  assertBj(item.published_at, 'news.published_at');
  assertBj(item.collected_at, 'news.collected_at');
  assertBj(item.created_at, 'news.created_at');
  for (const rel of item.related_sources || []) assertBj(rel.published_at, 'related_sources.published_at');
}
for (const item of newsData.items) checkNewsItem(item);

const times = newsData.items.map(x => Date.parse(x.published_at || x.collected_at || ''));
for (let i = 1; i < times.length; i++) {
  if (times[i] > times[i - 1]) throw new Error('news not sorted desc: ' + JSON.stringify(newsData.items.map(x => x.published_at)));
}

const clustered = newsData.items.find(x => (x.related_sources || []).length);
if (!clustered) throw new Error('expected clustered item with related_sources');

raw.prepare('INSERT INTO news_context (fingerprint,polymarket_json,community_json,query_terms,updated_at) VALUES (?,?,?,?,?)').run(
  fpD, null, JSON.stringify({ hn: [{ title: 't', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=9' }], reddit: [] }),
  '[]', '2026-01-15T06:00:00+00:00'
);
raw.prepare('INSERT INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)').run(
  fpD, '路透社', '国际政治', '脉搏测试', 'https://example.com/pulse', '', '2026-01-15T10:00:00Z', '2026-01-15T10:00:00Z', '待核实'
);

const realFetch = globalThis.fetch;
globalThis.fetch = async (url) => {
  const u = String(url);
  if (u.includes('gamma-api.polymarket.com')) return new Response(JSON.stringify([]), { status: 200 });
  if (u.includes('hn.algolia')) return new Response(JSON.stringify({ hits: [] }));
  if (u.includes('reddit.com')) return new Response(JSON.stringify({ data: { children: [] } }));
  return realFetch(url);
};

const pulse = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fpD + '&refresh=1'), env);
const pulseData = await pulse.json();
if (!pulseData.ok) throw new Error('pulse refresh failed');
assertBj(pulseData.updated_at, 'pulse.updated_at refresh');

const recentUtc = new Date(Date.now() - 5 * 60 * 1000).toISOString();
raw.prepare('UPDATE news_context SET updated_at = ?, community_json = ? WHERE fingerprint = ?').run(
  recentUtc,
  JSON.stringify({ hn: [{ title: 'cached', points: 1, num_comments: 1, discussion_url: 'https://news.ycombinator.com/item?id=1' }], reddit: [] }),
  fpD
);
const cached = await handler.fetch(new Request('http://x/api/pulse?fingerprint=' + fpD), env);
const cacheData = await cached.json();
if (!cacheData.cached) throw new Error('expected cached pulse');
assertBj(cacheData.updated_at, 'pulse.updated_at cached');

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

    def test_inline_script_vm_gate(self):
        script = ROOT / "tests" / "_inline_script_gate.mjs"
        script.write_text(INLINE_SCRIPT_GATE, encoding="utf-8")
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)

    def test_api_news_filters_sports(self):
        script = ROOT / "tests" / "_sports_filter.mjs"
        script.write_text(SPORTS_FILTER_SCRIPT, encoding="utf-8")
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)

    def test_api_news_clusters_same_event(self):
        script = ROOT / "tests" / "_cluster_news.mjs"
        script.write_text(CLUSTER_SCRIPT, encoding="utf-8")
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)

    def test_beijing_timezone_everywhere(self):
        script = ROOT / "tests" / "_beijing_timezone.mjs"
        script.write_text(BEIJING_TIMEZONE_SCRIPT, encoding="utf-8")
        try:
            r = subprocess.run(["node", str(script), str(ROOT)], capture_output=True, text=True, cwd=str(ROOT), timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("OK", r.stdout)
        finally:
            script.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()