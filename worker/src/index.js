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
   for(const e of b.source_errors||[]) statements.push(db.prepare("INSERT INTO source_runs (run_at,source_name,status,item_count,error) VALUES (?,?,?,?,?)").bind(b.run_at,e.source,"error",0,e.error));
   statements.push(db.prepare("UPDATE reports SET summary=CASE WHEN new_count>0 THEN '本轮新增 '||new_count||' 条新闻，待核实。' ELSE '本轮未收录新条目。' END WHERE id=(SELECT MAX(id) FROM reports) RETURNING new_count"));
   const results=await db.batch(statements);
   const inserted=results.at(-1).results[0].new_count;
   return json({ok:true,inserted,reported:true});
  }
  if(url.pathname==="/api/reports"||url.pathname==="/api/news"){
   if(!env.DB)return json({error:"database_not_configured"},503);
   if(url.pathname==="/api/reports"){const r=await env.DB.prepare("SELECT * FROM reports ORDER BY run_at DESC LIMIT 100").all();return json({items:r.results||[]})}
   const n=Math.min(Math.max((parseInt(url.searchParams.get("limit"),10)||50),1),100),c=url.searchParams.get("category");
   const q=c?env.DB.prepare("SELECT * FROM news_items WHERE title GLOB '*[一-鿿]*' AND category=? ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ?").bind(c,n):env.DB.prepare("SELECT * FROM news_items WHERE title GLOB '*[一-鿿]*' ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ?").bind(n);
   const r=await q.all();return json({items:r.results||[]});
  }
  if(url.pathname==="/")return new Response(PAGE,{headers:{"content-type":"text/html; charset=utf-8"}});
  return json({error:"not_found"},404);
 }
};
function cors(){return {"access-control-allow-origin":"*","access-control-allow-methods":"GET,POST,OPTIONS","access-control-allow-headers":"Authorization,Content-Type"}}
function json(v,s=200){return new Response(JSON.stringify(v),{status:s,headers:{...cors(),"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
const PAGE = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>全球新闻中心</title><style>
body{margin:0;background:#f3f5f9;color:#172033;font:16px system-ui,"PingFang SC",sans-serif}.wrap{max-width:1000px;margin:auto;padding:24px 16px}h1{margin:0;font-size:26px}.muted,.meta{color:#64748b;font-size:13px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.tabs button{border:1px solid #d6deea;background:white;border-radius:18px;padding:8px 13px}.tabs .active{background:#234bb5;color:white}.item,.report,.empty{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:10px 0}.item h2{font-size:18px;line-height:1.45;margin:8px 0}.item a{color:inherit;text-decoration:none}.item a:hover{text-decoration:underline}.summary{line-height:1.65;color:#334155;white-space:pre-wrap}.tag{background:#eef2ff;color:#3730a3;padding:3px 7px;border-radius:5px;font-size:12px}.empty{text-align:center;padding:40px;color:#64748b}@media(prefers-color-scheme:dark){body{background:#101827;color:#e5e7eb}.item,.report,.empty,.tabs button{background:#182235;color:#e5e7eb;border-color:#334155}.summary{color:#cbd5e1}.muted,.meta{color:#9ca3af}}</style><main class="wrap"><h1>全球新闻中心</h1><p class="muted">每 30 分钟更新 · 国际政治 / 人工智能与科技 / 财经金融 / 社会突发</p><div id="status" class="muted">正在连接…</div><nav class="tabs"><button class="active" data-cat="">全部</button><button data-cat="国际政治">国际政治</button><button data-cat="AI与科技">人工智能与科技</button><button data-cat="全球经济金融">全球经济金融</button><button data-cat="社会与突发">社会与突发</button><button data-cat="reports">采集记录</button></nav><section id="content"><div class="empty">加载中…</div></section></main><script>
const box=document.querySelector('#content'),status=document.querySelector('#status');let cat='';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let sequence=0;
const formatter=new Intl.DateTimeFormat('zh-CN',{dateStyle:'long',timeStyle:'short'});
function date(value){const d=new Date(value);return value && Number.isFinite(d.getTime())?formatter.format(d):'时间未知'}
async function load(){
 const id=++sequence,report=cat==='reports';
 try{
  const response=await fetch(report?'/api/reports':'/api/news'+(cat?'?category='+encodeURIComponent(cat):''));
  if(!response.ok)throw Error();
  const data=await response.json();
  if(id!==sequence)return;
  status.textContent='服务正常 · 时间按本地时区显示';
  box.innerHTML=data.items.map(x=>{
   if(report)return '<article class="report"><b>'+date(x.run_at)+'</b><p>本轮收录 '+esc(x.new_count)+' 条新条目</p><div class="meta">候选 '+esc(x.candidate_count)+' · 来源错误 '+esc(x.source_error_count)+'</div></article>';
   const title=esc(x.title),safe=/^https?:/i.test(x.url);
   return '<article class="item"><span class="tag">'+esc(x.category==='AI与科技'?'人工智能与科技':x.category)+'</span><h2>'+(safe?'<a target="_blank" rel="noopener noreferrer" href="'+esc(x.url)+'">'+title+'</a>':title)+'</h2><div class="meta">'+esc(x.source_name)+' · '+date(x.published_at||x.collected_at)+' · '+esc(x.verification_status)+'</div>'+(x.summary?'<p class="summary">'+esc(x.summary)+'</p>':'')+'</article>';
  }).join('')||'<div class="empty">暂无记录，等待下一轮采集。</div>';
 }catch{if(id===sequence){status.textContent='读取失败';box.innerHTML='<div class="empty">暂时无法读取数据，请稍后刷新。</div>'}}
}
document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-cat]').forEach(x=>x.classList.remove('active'));b.classList.add('active');cat=b.dataset.cat;load()});load();setInterval(load,60000);
</script></html>`;
