import editorial from "./editorial.json";
export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(request.method==="OPTIONS") return new Response(null,{headers:cors()});
  if(url.pathname==="/api/health") return json({ok:true,database:!!env.DB});
  if(url.pathname==="/api/ingest"&&request.method==="POST"){
   if(!env.INGEST_TOKEN||request.headers.get("Authorization")!=="Bearer "+env.INGEST_TOKEN)return json({error:"unauthorized"},401);
   if(!env.DB)return json({error:"database_not_configured"},503);
   let b;try{b=await request.json()}catch{return json({error:"invalid_json"},400)}
   if(!b||!Array.isArray(b.items)||!b.run_at)return json({error:"invalid_payload"},400);
   if(b.items.length>500 || !Array.isArray(b.source_errors||[]) || b.items.some(x=>!x || !x.fingerprint || !x.title || !x.category || !x.source_name || !/^https?:\/\//i.test(x.url))) return json({error:"invalid_payload"},400);
   const db=env.DB;
   const statements=[db.prepare("INSERT INTO reports (run_at,candidate_count,new_count,source_error_count,summary) VALUES (?,?,0,?,'')").bind(b.run_at,b.candidate_count||0,b.source_error_count||0)];
   // 同一事务内分组插入，逐组累计实际新增数；中途失败时整轮回滚。
   for(let i=0;i<b.items.length;i+=10){
    const group=b.items.slice(i,i+10);
    const values=group.flatMap(x=>[x.fingerprint,x.source_name,x.category,x.title,x.url,x.summary||"",x.published_at||null,x.collected_at||b.run_at,x.verification_status||"待核实"]);
    const placeholders=group.map(()=>"(?,?,?,?,?,?,?,?,?)").join(",");
    statements.push(db.prepare("INSERT OR IGNORE INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES "+placeholders).bind(...values));
    statements.push(db.prepare("UPDATE reports SET new_count=new_count+changes() WHERE id=(SELECT MAX(id) FROM reports)"));
   }
   statements.push(db.prepare("CREATE TABLE IF NOT EXISTS news_reading (fingerprint TEXT PRIMARY KEY,image_url TEXT,reading_text TEXT,short_body INTEGER)"));
   const enriched=b.items.filter(x=>x.image_url||x.reading_text);
   for(let i=0;i<enriched.length;i+=20){
    const group=enriched.slice(i,i+20);
    statements.push(db.prepare("INSERT OR REPLACE INTO news_reading VALUES "+group.map(()=>"(?,?,?,?)").join(",")).bind(...group.flatMap(x=>[x.fingerprint,x.image_url||"",x.reading_text||"",x.short_body?1:0])));
   }
   for(const e of b.source_errors||[]) statements.push(db.prepare("INSERT INTO source_runs (run_at,source_name,status,item_count,error) VALUES (?,?,?,?,?)").bind(b.run_at,e.source,"error",0,e.error));
   statements.push(db.prepare("UPDATE reports SET summary=CASE WHEN new_count>0 THEN '本轮新增 '||new_count||' 条新闻，待核实。' ELSE '本轮未收录新条目。' END WHERE id=(SELECT MAX(id) FROM reports) RETURNING new_count"));
   if(b.ranked && b.items.length){
    statements.splice(statements.length-1,0,db.prepare("CREATE TABLE IF NOT EXISTS current_board (id INTEGER PRIMARY KEY,payload TEXT NOT NULL)"),db.prepare("INSERT OR REPLACE INTO current_board VALUES(1,?)").bind(JSON.stringify(b.items)));
   }
   const results=await db.batch(statements);
   const inserted=results.at(-1).results[0].new_count;
   return json({ok:true,inserted,reported:true});
  }
  if(url.pathname==="/api/reports"||url.pathname==="/api/news"){
   if(!env.DB)return json({error:"database_not_configured"},503);
   if(url.pathname==="/api/reports"){const r=await env.DB.prepare("SELECT * FROM reports ORDER BY run_at DESC LIMIT 100").all();return json({items:r.results||[]})}
   const n=Math.min(Math.max((parseInt(url.searchParams.get("limit"),10)||50),1),100),c=url.searchParams.get("category");
   if(!await env.DB.prepare("SELECT name FROM sqlite_master WHERE name='current_board'").first())return json({items:[]});
   const board=await env.DB.prepare("SELECT payload FROM current_board WHERE id=1").first();
   const items=JSON.parse(board?.payload||"[]").filter(x=>!c||x.category===c).sort((a,b)=>Date.parse(b.published_at||b.collected_at)-Date.parse(a.published_at||a.collected_at)).slice(0,n);
   return json({items});
  }
  if(url.pathname==="/")return new Response(PAGE,{headers:{"content-type":"text/html; charset=utf-8"}});
  return json({error:"not_found"},404);
 }
};
function cors(){return {"access-control-allow-origin":"*","access-control-allow-methods":"GET,POST,OPTIONS","access-control-allow-headers":"Authorization,Content-Type"}}
function json(v,s=200){return new Response(JSON.stringify(v),{status:s,headers:{...cors(),"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
const PAGE = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>全球新闻中心</title><style>
body{margin:0;background:#f3f5f9;color:#172033;font:16px system-ui,"PingFang SC",sans-serif}.wrap{max-width:1000px;margin:auto;padding:24px 16px}h1{margin:0;font-size:26px}.muted,.meta{color:#64748b;font-size:13px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.tabs button{border:1px solid #d6deea;background:white;border-radius:18px;padding:8px 13px}.tabs .active{background:#234bb5;color:white}.item,.report,.empty{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:10px 0}.item h2{font-size:18px;line-height:1.45;margin:8px 0}.item a{color:inherit;text-decoration:none}.item a:hover{text-decoration:underline}.summary{line-height:1.65;color:#334155;white-space:pre-wrap}.tag{background:#eef2ff;color:#3730a3;padding:3px 7px;border-radius:5px;font-size:12px}.empty{text-align:center;padding:40px;color:#64748b}@media(prefers-color-scheme:dark){body{background:#101827;color:#e5e7eb}.item,.report,.empty,.tabs button{background:#182235;color:#e5e7eb;border-color:#334155}.summary{color:#cbd5e1}.muted,.meta{color:#9ca3af}}
:root{color-scheme:light}body{margin:0;background:#f7f6f2;color:#182c30;font-family:"PingFang SC","Microsoft YaHei",sans-serif}.wrap{max-width:760px;padding:36px 18px}.wrap>h1{font:700 clamp(32px,6vw,52px)/1.2 "Songti SC",serif;color:#183d3d}.tabs{position:sticky;top:0;z-index:2;background:#f7f6f2;overflow-x:auto;flex-wrap:nowrap;padding:12px 0;border-bottom:1px solid #bfcac5}.tabs button{flex:none;cursor:pointer;background:white;color:#294843;min-height:42px}.tabs .active{background:#19534b;color:white}.item,.report,.empty{background:white;color:#193139;padding:clamp(16px,4vw,32px);border-radius:12px}.item header,.item footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.item h2{font:700 clamp(19px,3vw,25px)/1.5 "Songti SC",serif;margin:14px 0}.item time,.item footer,.muted,.meta{color:#536a69;font-size:13px}.tag{background:#e2f0eb;color:#19534b}.summary{font-size:17px;line-height:1.85;color:#283d40}.photo{width:100%;max-height:410px;object-fit:contain;background:#f2f4f1;border-radius:6px}.item .more{display:inline-block;padding:10px 0;color:#18574f;font-weight:650}.item footer{border-top:1px solid #e2e8e5;margin-top:12px}.tabs button:focus-visible,a:focus-visible{outline:3px solid #a15d16}
</style><main class="wrap"><h1>全球新闻中心</h1><p class="muted">各站重点新闻 · 每站最多五条 · 按北京时间倒序</p><div id="status" class="muted">正在连接…</div><nav class="tabs"><button class="active" data-cat="">全部</button><button data-cat="国际政治">国际政治</button><button data-cat="AI与科技">人工智能与科技</button><button data-cat="全球经济金融">全球经济金融</button><button data-cat="社会与突发">社会与突发</button><button data-cat="reports">采集记录</button></nav><section id="content"><div class="empty">加载中…</div></section></main><script>
const box=document.querySelector('#content'),status=document.querySelector('#status');let cat='';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let sequence=0;
const formatter=new Intl.DateTimeFormat('zh-CN',{dateStyle:'long',timeStyle:'short',timeZone:'Asia/Shanghai'});
function date(value){const d=new Date(value);return value && Number.isFinite(d.getTime())?formatter.format(d):'时间未知'}
async function load(){
 const id=++sequence,report=cat==='reports';
 try{
  const response=await fetch(report?'/api/reports':'/api/news'+(cat?'?category='+encodeURIComponent(cat):''));
  if(!response.ok)throw Error();
  const data=await response.json();
  if(id!==sequence)return;
  status.textContent='北京时间（东八区）';
  box.innerHTML=data.items.map(x=>{
   if(report)return '<article class="report"><b>'+date(x.run_at)+'</b><p>本轮收录 '+esc(x.new_count)+' 条新条目</p><div class="meta">候选 '+esc(x.candidate_count)+' · 来源错误 '+esc(x.source_error_count)+'</div></article>';
   const title=esc(x.title),safe=/^https?:/i.test(x.url);
   const image=x.image_url && x.image_url.startsWith('https://')?'<img class="photo" loading="lazy" referrerpolicy="no-referrer" alt="报道配图" src="'+esc(x.image_url)+'" onerror="this.hidden=true">':'';
   const text=x.reading_text||x.summary||'';
   const link=safe?'<a class="more" target="_blank" rel="noopener noreferrer" href="'+esc(x.url)+'">'+(text && !x.short_body?'更多 · 阅读原文':'查看原文')+' ↗</a>':'';
   return '<article class="item"><header><span class="tag">'+esc(x.category==='AI与科技'?'人工智能与科技':x.category)+'</span><time>'+date(x.published_at||x.collected_at)+'</time></header><h2>'+title+'</h2>'+image+(text?'<p class="summary">'+esc(text)+'</p>':'')+'<footer><span>'+esc(x.source_name)+' · 待核实</span>'+link+'</footer></article>';
  }).join('')||'<div class="empty">暂无记录，等待下一轮采集。</div>';
 }catch{if(id===sequence){status.textContent='读取失败';box.innerHTML='<div class="empty">暂时无法读取数据，请稍后刷新。</div>'}}
}
document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-cat]').forEach(x=>x.classList.remove('active'));b.classList.add('active');cat=b.dataset.cat;load()});load();setInterval(load,60000);
</script></html>`;
