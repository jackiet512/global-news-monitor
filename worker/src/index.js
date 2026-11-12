export default {
 async fetch(request,env){
  const url=new URL(request.url);
  if(request.method==="OPTIONS") return new Response(null,{headers:cors()});
  if(url.pathname==="/api/health") return json({ok:true,database:!!env.DB});
  if(url.pathname==="/api/ingest"&&request.method==="POST"){
   if(!env.INGEST_TOKEN||request.headers.get("Authorization")!=="Bearer "+env.INGEST_TOKEN)return json({error:"unauthorized"},401);
   if(!env.DB)return json({error:"database_not_configured"},503);
   let b;try{b=await request.json()}catch{return json({error:"invalid_json"},400)}
   if(!Array.isArray(b.items)||!b.run_at)return json({error:"invalid_payload"},400);
   let inserted=0;
   for(const x of b.items.slice(0,500)){
    const r=await env.DB.prepare("INSERT OR IGNORE INTO news_items (fingerprint,source_name,category,title,url,summary,published_at,collected_at,verification_status) VALUES (?,?,?,?,?,?,?,?,?)").bind(x.fingerprint,x.source_name,x.category,x.title,x.url,x.summary||"",x.published_at,x.collected_at||b.run_at,x.verification_status||"待核实").run();
    inserted+=r.meta?.changes||0;
   }
   await env.DB.prepare("INSERT INTO reports (run_at,candidate_count,new_count,source_error_count,summary) VALUES (?,?,?,?,?)").bind(b.run_at,b.candidate_count||0,inserted,b.source_error_count||0,inserted?"本轮新增 "+inserted+" 条 RSS 候选；尚待核验。":"本轮无重大新增（或无新候选）；采集状态见运行记录。").run();
   for(const e of (b.source_errors||[]))await env.DB.prepare("INSERT INTO source_runs (run_at,source_name,status,item_count,error) VALUES (?,?,?,?,?)").bind(b.run_at,e.source,"error",0,e.error).run();
   return json({ok:true,inserted,reported:true});
  }
  if(url.pathname==="/api/reports"||url.pathname==="/api/news"){
   if(!env.DB)return json({error:"database_not_configured"},503);
   if(url.pathname==="/api/reports"){const r=await env.DB.prepare("SELECT * FROM reports ORDER BY run_at DESC LIMIT 100").all();return json({items:r.results||[]})}
   const n=Math.min(Math.max(Number(url.searchParams.get("limit")||50),1),100),c=url.searchParams.get("category");
   const q=c?env.DB.prepare("SELECT * FROM news_items WHERE category=? ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ?").bind(c,n):env.DB.prepare("SELECT * FROM news_items ORDER BY COALESCE(published_at,collected_at) DESC LIMIT ?").bind(n);
   const r=await q.all();return json({items:r.results||[]});
  }
  if(url.pathname==="/")return new Response(PAGE,{headers:{"content-type":"text/html; charset=utf-8"}});
  return json({error:"not_found"},404);
 }
};
function cors(){return {"access-control-allow-origin":"*","access-control-allow-methods":"GET,POST,OPTIONS","access-control-allow-headers":"Authorization,Content-Type"}}
function json(v,s=200){return new Response(JSON.stringify(v),{status:s,headers:{...cors(),"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
const PAGE = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>全球新闻中心</title><style>
body{margin:0;background:#f3f5f9;color:#172033;font:16px system-ui,"PingFang SC",sans-serif}.wrap{max-width:1000px;margin:auto;padding:24px 16px}h1{margin:0;font-size:26px}.muted,.meta{color:#64748b;font-size:13px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.tabs button{border:1px solid #d6deea;background:white;border-radius:18px;padding:8px 13px}.tabs .active{background:#234bb5;color:white}.item,.report,.empty{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:10px 0}.item h2{font-size:18px;line-height:1.45;margin:8px 0}.item a{color:inherit;text-decoration:none}.item a:hover{text-decoration:underline}.summary{line-height:1.65;color:#334155;white-space:pre-wrap}.tag{background:#eef2ff;color:#3730a3;padding:3px 7px;border-radius:5px;font-size:12px}.empty{text-align:center;padding:40px;color:#64748b}@media(prefers-color-scheme:dark){body{background:#101827;color:#e5e7eb}.item,.report,.empty,.tabs button{background:#182235;color:#e5e7eb;border-color:#334155}.summary{color:#cbd5e1}.muted,.meta{color:#9ca3af}}</style><main class="wrap"><h1>全球新闻中心</h1><p class="muted">每 30 分钟更新 · 国际政治 / AI 科技 / 财经金融 / 社会突发</p><div id="status" class="muted">正在连接…</div><nav class="tabs"><button class="active" data-cat="">全部</button><button data-cat="国际政治">国际政治</button><button data-cat="AI与科技">AI 与科技</button><button data-cat="全球经济金融">全球经济金融</button><button data-cat="社会与突发">社会与突发</button><button data-cat="reports">采集记录</button></nav><section id="content"><div class="empty">加载中…</div></section></main><script>
const box=document.querySelector('#content'),status=document.querySelector('#status');let cat='';
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function load(){try{let h=await fetch('/api/health').then(r=>r.json());status.textContent=h.database?'服务正常':'数据库尚未绑定';let report=cat==='reports',d=await fetch(report?'/api/reports':'/api/news'+(cat?'?category='+encodeURIComponent(cat):'')).then(r=>r.json());box.innerHTML=(d.items||[]).map(x=>report?'<article class="report"><b>'+esc(new Date(x.run_at).toLocaleString())+'</b><p>'+esc(x.summary)+'</p><div class="meta">候选 '+x.candidate_count+' · 新增 '+x.new_count+' · 来源错误 '+x.source_error_count+'</div></article>':'<article class="item"><span class="tag">'+esc(x.category)+'</span><h2><a target="_blank" rel="noopener" href="'+esc(x.url)+'">'+esc(x.title)+'</a></h2><div class="meta">'+esc(x.source_name)+' · '+esc(x.published_at||x.collected_at)+' · '+esc(x.verification_status)+'</div><p class="summary">'+esc(x.summary||'暂无摘要，请查看原始来源。')+'</p></article>').join('')||'<div class="empty">暂无记录，等待下一轮采集。</div>'}catch(e){status.textContent='连接异常';box.innerHTML='<div class="empty">暂时无法读取数据，请稍后刷新。</div>'}}
document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-cat]').forEach(x=>x.classList.remove('active'));b.classList.add('active');cat=b.dataset.cat;load()});load();setInterval(load,60000);
</script></html>`;
