export default {
 async scheduled(controller,env,ctx){
  ctx.waitUntil(runGitHubScheduleFallback(env));
 },
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
   b.run_at=toBeijingIso(b.run_at);
   for(const x of b.items){x.published_at=toBeijingIso(x.published_at)||null;x.collected_at=toBeijingIso(x.collected_at)||b.run_at}
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
   statements.push(db.prepare("CREATE TABLE IF NOT EXISTS news_context (fingerprint TEXT PRIMARY KEY,polymarket_json TEXT,community_json TEXT,query_terms TEXT,updated_at TEXT NOT NULL)"));
   const ctxRows=b.items.filter(x=>x.polymarket||x.community||x.query_terms||x.hn_meta);
   for(const row of ctxRows){
    const community=row.community?{...row.community}:row.hn_meta?{hn_meta:row.hn_meta}:{};
    if(row.hn_meta) community.hn_meta=row.hn_meta;
    const pm=safeJsonString(row.polymarket,8000),cm=safeJsonString(Object.keys(community).length?community:null,16000),qt=safeJsonString(row.query_terms,2000);
    if(pm||cm||qt) statements.push(db.prepare("INSERT OR REPLACE INTO news_context (fingerprint,polymarket_json,community_json,query_terms,updated_at) VALUES (?,?,?,?,?)").bind(row.fingerprint,pm,cm,qt,b.run_at));
   }
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
   const selected=url.searchParams.get("date")||beijingDate();
   if(!validDate(selected))return json({error:"invalid_date"},400);
   const from=selected+"T00:00:00+08:00",to=nextDate(selected)+"T00:00:00+08:00";
   if(url.pathname==="/api/reports"){
    const r=await env.DB.prepare("SELECT * FROM reports WHERE julianday(run_at)>=julianday(?) AND julianday(run_at)<julianday(?) ORDER BY julianday(run_at) DESC LIMIT 200").bind(from,to).all();
    const items=(r.results||[]).map(row=>({...row,run_at:toBeijingIso(row.run_at),created_at:toBeijingIso(row.created_at)}));
    return json({date:selected,items});
   }
   await env.DB.prepare("CREATE TABLE IF NOT EXISTS news_reading (fingerprint TEXT PRIMARY KEY,image_url TEXT,reading_text TEXT,short_body INTEGER)").run();
   await env.DB.prepare("CREATE TABLE IF NOT EXISTS news_context (fingerprint TEXT PRIMARY KEY,polymarket_json TEXT,community_json TEXT,query_terms TEXT,updated_at TEXT NOT NULL)").run();
   const n=Math.min(Math.max((parseInt(url.searchParams.get("limit"),10)||100),1),200),c=url.searchParams.get("category"),fetchLimit=Math.min(Math.max(n*3,120),250);
   const sql="SELECT ni.*,nr.image_url,nr.reading_text,nr.short_body,nc.polymarket_json,nc.community_json,nc.query_terms FROM news_items ni LEFT JOIN news_reading nr ON nr.fingerprint=ni.fingerprint LEFT JOIN news_context nc ON nc.fingerprint=ni.fingerprint WHERE julianday(COALESCE(ni.published_at,ni.collected_at))>=julianday(?) AND julianday(COALESCE(ni.published_at,ni.collected_at))<julianday(?)"+(c?" AND ni.category=?":"")+" ORDER BY julianday(COALESCE(ni.published_at,ni.collected_at)) DESC LIMIT ?";
   const q=env.DB.prepare(sql),r=c?await q.bind(from,to,c,fetchLimit).all():await q.bind(from,to,fetchLimit).all();
   const items=(r.results||[]).map(row=>{
    const community=parseJsonField(row.community_json)||{};
    const hn_meta=community.hn_meta||null;
    const cleanCommunity={hn:community.hn||[],reddit:community.reddit||[]};
    return {...row,polymarket:parseJsonField(row.polymarket_json),community:cleanCommunity,hn_meta,query_terms:parseJsonField(row.query_terms),polymarket_json:undefined,community_json:undefined};
   }).filter(row=>!isSportsItem(row));
   const clustered=clusterNewsItems(items).sort((a,b)=>Date.parse(b.published_at||b.collected_at||"")-Date.parse(a.published_at||a.collected_at||"")).slice(0,n).map(normalizeNewsTimes);
   return json({date:selected,items:clustered});
  }
  if(url.pathname==="/api/pulse"){
   if(!env.DB)return json({error:"database_not_configured"},503);
   const fp=url.searchParams.get("fingerprint")||"";
   if(!/^[a-f0-9]{64}$/i.test(fp))return json({error:"invalid_fingerprint"},400);
   await env.DB.prepare("CREATE TABLE IF NOT EXISTS news_context (fingerprint TEXT PRIMARY KEY,polymarket_json TEXT,community_json TEXT,query_terms TEXT,updated_at TEXT NOT NULL)").run();
   const row=await env.DB.prepare("SELECT ni.title,ni.url,nc.polymarket_json,nc.community_json,nc.query_terms,nc.updated_at FROM news_items ni LEFT JOIN news_context nc ON nc.fingerprint=ni.fingerprint WHERE ni.fingerprint=?").bind(fp).first();
   if(!row)return json({error:"not_found"},404);
   const refresh=url.searchParams.get("refresh")==="1";
   let polymarket=parseJsonField(row.polymarket_json),communityRaw=parseJsonField(row.community_json)||{hn:[],reddit:[]},queryTerms=parseJsonField(row.query_terms)||[];
   const cachedAt=row.updated_at?Date.parse(row.updated_at):0;
   const fresh=cachedAt && Date.now()-cachedAt<30*60*1000;
   const cleanCommunity=cleanPulseCommunity(communityRaw);
   const hasCommunity=cleanCommunity.hn.length||cleanCommunity.reddit.length;
   if(!refresh&&fresh&&hasCommunity){
    return json({ok:true,fingerprint:fp,cached:true,polymarket,community:cleanCommunity,query_terms:queryTerms,source_status:{hn:cleanCommunity.hn.length?"ok":"empty",reddit:cleanCommunity.reddit.length?"ok":"empty",polymarket:polymarket?"ok":"empty"},updated_at:toBeijingIso(row.updated_at)});
   }
   const q=(Array.isArray(queryTerms)&&queryTerms.length?queryTerms.join(" "):extractTerms(row.title)).trim();
   const sourceStatus={hn:"empty",reddit:"empty",polymarket:polymarket?"ok":"empty"};
   if(!q){
    const updated=toBeijingIso(Date.now());
    await env.DB.prepare("INSERT OR REPLACE INTO news_context (fingerprint,polymarket_json,community_json,query_terms,updated_at) VALUES (?,?,?,?,?)").bind(fp,safeJsonString(polymarket,8000),safeJsonString(communityRaw,16000),safeJsonString(queryTerms,2000),updated).run();
    return json({ok:true,fingerprint:fp,cached:false,polymarket,community:cleanPulseCommunity(communityRaw),query_terms:queryTerms,source_status:sourceStatus,updated_at:updated});
   }
   const [hnSettle,redditSettle,pmSettle]=await Promise.allSettled([fetchHn(q),fetchReddit(q),polymarket?Promise.resolve(polymarket):fetchPolymarket(q)]);
   if(hnSettle.status==="fulfilled"){
    const hn=hnSettle.value;
    sourceStatus.hn=hn===null?"unavailable":(hn.length?"ok":"empty");
    if(hn?.length) communityRaw={...communityRaw,hn:mergeDiscussions(communityRaw.hn,hn)};
   }else sourceStatus.hn="unavailable";
   if(redditSettle.status==="fulfilled"){
    const rd=redditSettle.value;
    sourceStatus.reddit=rd===null?"unavailable":(rd.length?"ok":"empty");
    if(rd?.length) communityRaw={...communityRaw,reddit:rd};
   }else sourceStatus.reddit="unavailable";
   if(!polymarket&&pmSettle.status==="fulfilled"){
    polymarket=pmSettle.value;
    sourceStatus.polymarket=polymarket?"ok":"empty";
   }else if(!polymarket) sourceStatus.polymarket="unavailable";
   const updated=toBeijingIso(Date.now());
   await env.DB.prepare("INSERT OR REPLACE INTO news_context (fingerprint,polymarket_json,community_json,query_terms,updated_at) VALUES (?,?,?,?,?)").bind(fp,safeJsonString(polymarket,8000),safeJsonString(communityRaw,16000),safeJsonString(queryTerms,2000),updated).run();
   return json({ok:true,fingerprint:fp,cached:false,polymarket,community:cleanPulseCommunity(communityRaw),query_terms:queryTerms,source_status:sourceStatus,updated_at:updated});
  }
  if(url.pathname==="/api/collect" && request.method==="POST"){
   if(request.headers.get("Origin")!==url.origin)return json({error:"origin"},403);
   if(!env.GITHUB_ACTIONS_TOKEN)return json({error:"setup"},503);
   await env.DB.prepare("CREATE TABLE IF NOT EXISTS manual_dispatch(id INTEGER PRIMARY KEY, started INTEGER NOT NULL)").run();
   const now=Date.now();
   const claim=await env.DB.prepare("INSERT INTO manual_dispatch VALUES(1,?) ON CONFLICT(id) DO UPDATE SET started=excluded.started WHERE started<?").bind(now,now-600000).run();
   if(!claim.meta.changes)return json({error:"recent"},429);
   try{
    const dispatch=await fetch("https://api.github.com/repos/jackiet512/global-news-monitor/actions/workflows/collect.yml/dispatches",{method:"POST",headers:{Authorization:"Bearer "+env.GITHUB_ACTIONS_TOKEN,Accept:"application/vnd.github+json","Content-Type":"application/json","User-Agent":"GlobalNewsMonitor"},body:JSON.stringify({ref:"main",return_run_details:true})});
    if(!dispatch.ok)throw Error();
    const detail=dispatch.status===204?{}:await dispatch.json();
    return json({submitted:true,run_id:detail.workflow_run_id||null},202);
   }catch{
    await env.DB.prepare("DELETE FROM manual_dispatch WHERE id=1 AND started=?").bind(now).run();
    return json({error:"dispatch"},502);
   }
  }
  if(url.pathname==="/")return new Response(env.GITHUB_ACTIONS_TOKEN?PAGE:PAGE.replace('<button type="button" id="collect">手动采集最新新闻</button>','<button type="button" id="collect">手动采集最新新闻 ↗</button>').replace('trigger.onclick=async()=>{',`trigger.onclick=async()=>{window.open('https://github.com/jackiet512/global-news-monitor/actions/workflows/collect.yml','_blank','noopener');notice.textContent='请在 GitHub 点击 Run workflow，选择 main 并确认运行。完成后可在本站查看采集记录。';return;`),{headers:{"content-type":"text/html; charset=utf-8"}});
  return json({error:"not_found"},404);
 }
};
async function runGitHubScheduleFallback(env){
 const token=env.GITHUB_ACTIONS_TOKEN;
 if(!token){console.error("schedule-fallback: missing GITHUB_ACTIONS_TOKEN");return}
 const headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28","User-Agent":"GlobalNewsMonitor-ScheduleFallback"};
 const endpoint="https://api.github.com/repos/jackiet512/global-news-monitor/actions/workflows/collect.yml/runs?branch=main&per_page=10";
 try{
  const response=await fetch(endpoint,{headers});
  if(!response.ok)throw new Error("list workflow runs HTTP "+response.status+" "+(await response.text()).slice(0,300));
  const data=await response.json();
  const latest=(data.workflow_runs||[]).sort((a,b)=>Date.parse(b.created_at)-Date.parse(a.created_at))[0];
  const age=latest?Date.now()-Date.parse(latest.created_at):Number.POSITIVE_INFINITY;
  const stale=!latest||!Number.isFinite(age)||age>45*60*1000;
  if(!stale){
   console.log("schedule-fallback: recent workflow run exists",JSON.stringify({id:latest.id,status:latest.status,event:latest.event,age_minutes:Math.round(age/60000)}));
   return;
  }
  const dispatch=await fetch("https://api.github.com/repos/jackiet512/global-news-monitor/actions/workflows/collect.yml/dispatches",{method:"POST",headers:{...headers,"Content-Type":"application/json"},body:JSON.stringify({ref:"main"})});
  if(dispatch.status!==204)throw new Error("workflow dispatch HTTP "+dispatch.status+" "+(await dispatch.text()).slice(0,300));
  console.log("schedule-fallback: dispatched collector because latest run was stale",JSON.stringify({previous_run_id:latest?.id||null,age_minutes:Number.isFinite(age)?Math.round(age/60000):null}));
 }catch(error){console.error("schedule-fallback failed",String(error))}
}
const SPORTS_EMERGENCY_ZH=/伤亡|遇难|踩踏|枪击|爆炸|恐袭|地震|预警|疏散|应急响应/;
const SPORTS_EMERGENCY_EN=/\b(casualties|stampede|shooting|explosion|terror|evacuat)\w*\b/i;
const SPORTS_PATH=/\/(?:sports?|football|soccer|nba|nfl|mlb|nhl|cricket|rugby|tennis|golf|f1|formula1|olympics|athletics|boxing|ufc|mma|baseball|basketball)(?:\/|$)/i;
const SPORTS_EN=/\b(?:nba|nfl|mlb|nhl|wnba|ncaa|fifa|uefa|premier league|champions league|la liga|serie a|bundesliga|super bowl|world cup|wimbledon|grand prix|formula 1|f1|ufc|mma|boxing|cricket|rugby|tennis|baseball|basketball|badminton|table tennis|golf|pga|nascar|motogp|marathon|playoffs|quarterback|touchdown|home run|goalkeeper|hat-trick|red card|penalty kick|transfer window|esports)\b/i;
const SPORTS_ZH=/英超|欧冠|西甲|意甲|德甲|法甲|中超|CBA|NBA|NFL|MLB|NHL|UFC|F1|WTA|ATP|世预赛|世界杯|欧洲杯|美洲杯|亚洲杯|亚冠|大满贯|温网|法网|美网|澳网|冬奥会|奥运会|亚运会|全运会|超级碗|季后赛|总决赛|常规赛|全明星赛|男足|女足|男篮|女篮|男排|女排|国足|国乒|国羽|足球|篮球|网球|排球|乒乓球|羽毛球|棒球|橄榄球|高尔夫|台球|斯诺克|拳击|田径|马拉松|花样滑冰|短道速滑|跳水|体操|电竞|球星|球员|门将|前锋|后卫|主帅|主教练|转会|绝杀|点球|红牌|黄牌|加时赛|三分球|扣篮|篮板|助攻|帽子戏法|卫冕冠军|晋级八强|晋级四强|晋级决赛/;
const EVENT_ALIASES={"丧生":["死亡","身亡","遇难","致死","毙命"],"风暴":["大风暴","暴风雨","强风暴"],"导致":["带来","造成","引发","致使"],"袭击":["袭击事件","空袭","无人机袭击"],"否认":["驳斥","拒绝承认"],"指控":["指责","控告"]};
const ZH_EVENT_STOP=new Set("的在中给被对此和与、，了将称表示强大".split(""));
const CONFLICT_ENTITY_GROUPS=[["法国","意大利","日本","德国","英国","爱尔兰","加拿大","美国","科威特","伊朗","中国","俄罗斯","乌克兰","以色列"],["OpenAI","Anthropic","谷歌","微软","苹果","亚马逊"],["美联储","欧洲央行","日本央行","英国央行"]];
function normalizeEventTitle(title){
 let norm=String(title||"");
 for(const [standard,aliases] of Object.entries(EVENT_ALIASES)){
  for(const alias of [...aliases].sort((a,b)=>b.length-a.length)) norm=norm.split(alias).join(standard);
 }
 return norm;
}
function zhEventBigrams(text){
 const grams=new Set();
 for(const part of String(text||"").match(/[\u4e00-\u9fff]+/g)||[]){
  const clean=[...part].filter(c=>!ZH_EVENT_STOP.has(c)).join("");
  for(let i=0;i<clean.length-1;i++) grams.add(clean.slice(i,i+2));
 }
 return grams;
}
function eventEntities(text){
 const found=[];
 for(const group of CONFLICT_ENTITY_GROUPS){
  for(const entity of group) if(text.includes(entity)) found.push({group,entity});
 }
 return found;
}
function hasEventEntityConflict(a,b){
 const entsA=eventEntities(a),entsB=eventEntities(b);
 for(const group of CONFLICT_ENTITY_GROUPS){
  const inA=new Set(entsA.filter(x=>x.group===group).map(x=>x.entity));
  const inB=new Set(entsB.filter(x=>x.group===group).map(x=>x.entity));
  if(inA.size&&inB.size&&!([...inA].some(x=>inB.has(x)))) return true;
 }
 return false;
}
function englishEventWords(title){
 const stop=new Set("the and for from with says after into amid that this news how his her are has more live video over why new their about was its".split(" "));
 return new Set((String(title||"").toLowerCase().match(/[a-z]{3,}/g)||[]).filter(w=>!stop.has(w)).map(w=>w.replace(/s$/,"")));
}
function newsItemsSameEvent(a,b){
 const tsA=Date.parse(a.published_at||a.collected_at||""),tsB=Date.parse(b.published_at||b.collected_at||"");
 if(!Number.isFinite(tsA)||!Number.isFinite(tsB)||Math.abs(tsA-tsB)>3*86400000) return false;
 const normA=normalizeEventTitle(a.title),normB=normalizeEventTitle(b.title);
 if(hasEventEntityConflict(normA,normB)) return false;
 const wordsA=englishEventWords(a.title),wordsB=englishEventWords(b.title);
 const gramsA=zhEventBigrams(normA),gramsB=zhEventBigrams(normB);
 const shared=[...wordsA].filter(w=>wordsB.has(w));
 const common=[...gramsA].filter(g=>gramsB.has(g));
 const en=shared.length/Math.max(1,Math.min(wordsA.size,wordsB.size));
 const zh=common.length/Math.max(1,Math.min(gramsA.size,gramsB.size));
 if(common.length>=4&&zh>=0.40) return true;
 return (shared.length>=4&&en>=0.60&&common.length>=3)||(common.length>=6&&zh>=0.52)||(shared.length>=3&&en>=0.50&&common.length>=6&&zh>=0.33);
}
function mergeDiscussionsByUrl(a,b){
 const out=[...(a||[])];
 for(const x of b||[]){
  if(!out.some(y=>y.discussion_url===x.discussion_url||(y.title&&x.title&&y.title===x.title))) out.push(x);
 }
 return out;
}
function mergeRedditByUrl(a,b){
 const out=[...(a||[])];
 for(const x of b||[]){
  if(!out.some(y=>y.url===x.url||(y.title&&x.title&&y.title===x.title))) out.push(x);
 }
 return out;
}
function itemRichness(row){
 const textLen=(row.reading_text||row.summary||"").length;
 const hasImg=row.image_url?1:0;
 const ts=Date.parse(row.published_at||row.collected_at||"")||0;
 return {textLen,hasImg,ts};
}
function pickClusterPrimary(cluster){
 return [...cluster].sort((a,b)=>{const ra=itemRichness(a),rb=itemRichness(b);if(rb.textLen!==ra.textLen) return rb.textLen-ra.textLen;if(rb.hasImg!==ra.hasImg) return rb.hasImg-ra.hasImg;return rb.ts-ra.ts})[0];
}
function mergeNewsCluster(cluster){
 if(cluster.length<=1) return cluster[0];
 const primary=pickClusterPrimary(cluster);
 const others=cluster.filter(x=>x.fingerprint!==primary.fingerprint);
 const related_sources=[];
 const seenUrl=new Set();
 for(const row of others){
  if(!row.url||seenUrl.has(row.url)) continue;
  seenUrl.add(row.url);
  related_sources.push({source_name:row.source_name||"",title:row.title||"",url:row.url||"",published_at:row.published_at||row.collected_at||""});
 }
 let image_url=primary.image_url||"";
 let polymarket=primary.polymarket||null;
 let community={hn:[...(primary.community?.hn||[])],reddit:[...(primary.community?.reddit||[])]};
 for(const row of others){
  if(!image_url&&row.image_url) image_url=row.image_url;
  if(!polymarket&&row.polymarket) polymarket=row.polymarket;
  community={hn:mergeDiscussionsByUrl(community.hn,row.community?.hn),reddit:mergeRedditByUrl(community.reddit,row.community?.reddit)};
 }
 return {...primary,image_url,polymarket,community,related_sources,source_count:1+related_sources.length};
}
function clusterNewsItems(items){
 if(!items?.length) return [];
 const parent=items.map((_,i)=>i);
 const find=i=>{while(parent[i]!==i){parent[i]=parent[parent[i]];i=parent[i]}return i};
 const unite=(a,b)=>{const ra=find(a),rb=find(b);if(ra!==rb)parent[ra]=rb};
 for(let i=0;i<items.length;i++) for(let j=i+1;j<items.length;j++) if(newsItemsSameEvent(items[i],items[j])) unite(i,j);
 const groups=new Map();
 for(let i=0;i<items.length;i++){const root=find(i);if(!groups.has(root))groups.set(root,[]);groups.get(root).push(items[i])}
 return [...groups.values()].map(mergeNewsCluster);
}
function isSportsItem(row){
 const text=[row.title||"",row.summary||""].filter(Boolean).join(" ");
 if(SPORTS_EMERGENCY_ZH.test(text)||SPORTS_EMERGENCY_EN.test(text))return false;
 let path="";
 try{path=new URL(row.url||"").pathname.toLowerCase()}catch{}
 if(SPORTS_PATH.test(path))return true;
 if(SPORTS_EN.test(text)||SPORTS_ZH.test(text))return true;
 return false;
}
function toBeijingIso(value){
 if(value==null||value==="")return value||null;
 if(typeof value==="number"&&Number.isFinite(value)){
  const ms=value>1e12?value:value*1000;
  if(!Number.isFinite(Date.parse(new Date(ms).toISOString())))return value||null;
  return formatBeijingMs(ms);
 }
 let text=String(value).trim();
 if(!text)return value||null;
 if(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(text))text=text.replace(" ","T")+"Z";
 else text=text.replace(/Z$/,"+00:00");
 const parsed=Date.parse(text);
 if(!Number.isFinite(parsed))return value||null;
 return formatBeijingMs(parsed);
}
function formatBeijingMs(ms){
 const t=ms+8*3600000,u=new Date(t);
 const y=u.getUTCFullYear(),m=String(u.getUTCMonth()+1).padStart(2,"0"),d=String(u.getUTCDate()).padStart(2,"0");
 const h=String(u.getUTCHours()).padStart(2,"0"),mi=String(u.getUTCMinutes()).padStart(2,"0"),s=String(u.getUTCSeconds()).padStart(2,"0");
 return `${y}-${m}-${d}T${h}:${mi}:${s}+08:00`;
}
function normalizeNewsTimes(row){
 const related=(row.related_sources||[]).map(r=>({...r,published_at:toBeijingIso(r.published_at)}));
 return {...row,published_at:toBeijingIso(row.published_at),collected_at:toBeijingIso(row.collected_at),created_at:toBeijingIso(row.created_at),related_sources:related};
}
function cors(){return {"access-control-allow-origin":"*","access-control-allow-methods":"GET,POST,OPTIONS","access-control-allow-headers":"Authorization,Content-Type"}}
function json(v,s=200){return new Response(JSON.stringify(v),{status:s,headers:{...cors(),"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
function beijingDate(){const p=new Intl.DateTimeFormat("en-US",{timeZone:"Asia/Shanghai",year:"numeric",month:"2-digit",day:"2-digit"}).formatToParts(new Date()).reduce((a,x)=>(a[x.type]=x.value,a),{});return p.year+"-"+p.month+"-"+p.day}
function validDate(s){if(!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(s))return false;const d=new Date(s+"T00:00:00Z");return Number.isFinite(d.getTime())&&d.toISOString().slice(0,10)===s}
function nextDate(s){const d=new Date(s+"T00:00:00Z");d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10)}
function parseJsonField(raw){if(raw==null||raw==="")return null;try{return JSON.parse(raw)}catch{return null}}
function safeJsonString(v,max){if(v==null)return null;try{const s=JSON.stringify(v);return s.length>max?null:s}catch{return null}}
function extractTerms(title){return String(title||"").split(/[^a-zA-Z\u4e00-\u9fff]+/).filter(w=>w.length>2).slice(0,6).join(" ")}
function cleanPulseCommunity(c){const raw=c||{};return {hn:Array.isArray(raw.hn)?raw.hn:[],reddit:Array.isArray(raw.reddit)?raw.reddit:[]};}
function mergeDiscussions(a,b){const out=[...(a||[])];for(const x of b||[]){if(!out.some(y=>y.discussion_url===x.discussion_url||y.title===x.title))out.push(x)}return out}
const PM_STOP=new Set("will the and for with what when before after president market world global news says report china united states us ai model new year month from that this into over than have been were about their there which while during 2024 2025 2026 2027".split(" "));
function pmTokens(t){return new Set(String(t||"").toLowerCase().match(/[a-z]{3,}/g)?.filter(w=>!PM_STOP.has(w))||[])}
function parsePmList(v){if(v==null)return [];if(Array.isArray(v))return v;if(typeof v==="string"){try{const p=JSON.parse(v);return Array.isArray(p)?p:[]}catch{return []}}return []}
function pmMarketProb(mk){
 const outcomes=parsePmList(mk.outcomes),prices=parsePmList(mk.outcomePrices);
 if(!outcomes.length||outcomes.length!==prices.length||mk.closed)return null;
 const floats=prices.map(p=>+p);if(floats.every(v=>!v))return null;
 const yi=outcomes.findIndex(o=>String(o).toLowerCase()==="yes");
 if(yi>=0)return {outcome:"Yes",probability:Math.round(floats[yi]*100),question:String(mk.question||"")};
 const bi=floats.indexOf(Math.max(...floats));
 return {outcome:String(outcomes[bi]),probability:Math.round(floats[bi]*100),question:String(mk.question||"")};
}
function pmFmtVol(v){const n=+v||0;if(n>=1e6)return "$"+(n/1e6).toFixed(1)+"M";if(n>=1e3)return "$"+Math.round(n/1e3)+"K";return n>0?"$"+Math.round(n):""}
function matchPmEvent(events,query){
 const qt=pmTokens(query);if(qt.size<2)return null;
 let best=null,bestScore=0;
 for(const ev of events||[]){
  const slug=ev.slug||"",vol=pmFmtVol(ev.volume||ev.volume24hr||0);
  for(const mk of ev.markets||[]){
   const prob=pmMarketProb(mk);if(!prob)continue;
   const title=String(ev.title||""),et=pmTokens(title+" "+prob.question);
   const shared=[...qt].filter(w=>et.has(w));if(shared.length<2)continue;
   const score=shared.length;if(score>bestScore){bestScore=score;best={event_title:title,question:prob.question,outcome:prob.outcome,probability:prob.probability,volume_text:vol,url:slug?"https://polymarket.com/event/"+slug:""};}
  }
 }
 return bestScore>=2?best:null;
}
async function fetchHn(query){
 const u="https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=5&query="+encodeURIComponent(query);
 const r=await fetch(u,{headers:{"User-Agent":"GlobalNewsMonitor/1.0"},signal:AbortSignal.timeout(5000)});
 if(!r.ok)return null;
 const data=await r.json();
 return (data.hits||[]).map(h=>({title:h.title||h.story_title||"",points:+(h.points||0),num_comments:+(h.num_comments||0),discussion_url:h.objectID?"https://news.ycombinator.com/item?id="+h.objectID:"",url:h.url||""}));
}
async function fetchReddit(query){
 const u="https://www.reddit.com/search.json?q="+encodeURIComponent(query)+"&sort=relevance&t=month&limit=5&raw_json=1";
 const r=await fetch(u,{headers:{"User-Agent":"GlobalNewsMonitor/1.0"},signal:AbortSignal.timeout(5000)});
 if(!r.ok)return null;
 const data=await r.json();
 return ((data.data||{}).children||[]).map(c=>{const p=c.data||{};return {subreddit:p.subreddit||"",title:p.title||"",score:+(p.score||0),num_comments:+(p.num_comments||0),url:p.permalink?"https://www.reddit.com"+p.permalink:""}});
}
async function fetchPolymarket(query){
 const r=await fetch("https://gamma-api.polymarket.com/events?active=true&closed=false&limit=80",{headers:{"User-Agent":"GlobalNewsMonitor/1.0"},signal:AbortSignal.timeout(5000)});
 if(!r.ok)throw new Error("polymarket http "+r.status);
 const events=await r.json();
 return matchPmEvent(events,query);
}
const PAGE = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>全球新闻中心</title><style>
body{margin:0;background:#f3f5f9;color:#172033;font:16px system-ui,"PingFang SC",sans-serif}.wrap{max-width:1000px;margin:auto;padding:24px 16px}h1{margin:0;font-size:26px}.muted,.meta{color:#64748b;font-size:13px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0}.tabs button{border:1px solid #d6deea;background:white;border-radius:18px;padding:8px 13px}.tabs .active{background:#234bb5;color:white}.item,.report,.empty{background:white;border:1px solid #e2e8f0;border-radius:12px;padding:16px;margin:10px 0}.item h2{font-size:18px;line-height:1.45;margin:8px 0}.item a{color:inherit;text-decoration:none}.item a:hover{text-decoration:underline}.summary{line-height:1.65;color:#334155;white-space:pre-wrap}.tag{background:#eef2ff;color:#3730a3;padding:3px 7px;border-radius:5px;font-size:12px}.empty{text-align:center;padding:40px;color:#64748b}@media(prefers-color-scheme:dark){body{background:#101827;color:#e5e7eb}.item,.report,.empty,.tabs button{background:#182235;color:#e5e7eb;border-color:#334155}.summary{color:#cbd5e1}.muted,.meta{color:#9ca3af}}
.datebar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;background:white;border:1px solid #dce5df;border-radius:12px;padding:12px;margin:18px 0}.datebar input,.datebar button{font:inherit;border:1px solid #d5dfd9;border-radius:8px;background:white;color:#24443e;padding:9px;min-height:40px}.datebar button{cursor:pointer}.datebar b{margin-right:auto;color:#193f3b}@media(max-width:520px){.datebar{gap:6px}.datebar b{width:100%}.datebar button,.datebar input{flex:1;min-width:0}}:root{color-scheme:light}body{margin:0;background:#f7f6f2;color:#182c30;font-family:"PingFang SC","Microsoft YaHei",sans-serif}.wrap{max-width:760px;padding:36px 18px}.wrap>h1{font:700 clamp(32px,6vw,52px)/1.2 "Songti SC",serif;color:#183d3d}.tabs{position:sticky;top:0;z-index:2;background:#f7f6f2;overflow-x:auto;flex-wrap:nowrap;padding:12px 0;border-bottom:1px solid #bfcac5}.tabs button{flex:none;cursor:pointer;background:white;color:#294843;min-height:42px}.tabs .active{background:#19534b;color:white}.item,.report,.empty{background:white;color:#193139;padding:clamp(16px,4vw,32px);border-radius:12px}.item header,.item footer{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.item h2{font:700 clamp(19px,3vw,25px)/1.5 "Songti SC",serif;margin:14px 0}.item time,.item footer,.muted,.meta{color:#536a69;font-size:13px}.tag{background:#e2f0eb;color:#19534b}.summary{font-size:17px;line-height:1.85;color:#283d40}.photo{width:100%;max-height:410px;object-fit:contain;background:#f2f4f1;border-radius:6px}.item .more{display:inline-block;padding:10px 0;color:#18574f;font-weight:650}.item footer{border-top:1px solid #e2e8e5;margin-top:12px}.tabs button:focus-visible,a:focus-visible{outline:3px solid #a15d16}.pmcap{display:inline-flex;align-items:center;gap:6px;background:#eef6ff;border:1px solid #b8d4f0;color:#1e4a7a;border-radius:16px;padding:4px 10px;font-size:12px;margin:6px 0}.hnmeta{font-size:12px;color:#6b5b3e;margin:4px 0}.pulse-btn{margin-top:10px;border:1px solid #c5d4cf;background:#f4faf7;color:#19534b;border-radius:8px;padding:8px 12px;cursor:pointer;font:inherit}.pulse-drawer{margin-top:10px;padding:12px;border:1px solid #d7e2dd;border-radius:8px;background:#fafcfa;font-size:14px}.pulse-drawer h3{font-size:14px;margin:8px 0 4px}.pulse-drawer ul{margin:0;padding-left:18px}.pulse-drawer li{margin:4px 0}.pulse-loading{color:#64748b;font-size:13px}.multi-src{font-size:12px;color:#19534b;background:#e8f2ed;border:1px solid #b9cfc4;border-radius:14px;padding:3px 9px;margin:4px 0;display:inline-block}.related-sources{margin-top:10px;font-size:13px;color:#425b59}.related-sources summary{cursor:pointer;color:#18574f;font-weight:600}.related-sources ul{margin:6px 0 0;padding-left:18px}.related-sources li{margin:4px 0;line-height:1.5}
</style><main class="wrap"><h1>全球新闻中心</h1><p class="muted">各站重点新闻 · 每站最多五条 · 按北京时间倒序</p><div id="status" class="muted">正在连接…</div><section class="datebar"><button type="button" id="collect">手动采集最新新闻</button><b id="dateTitle">当天新闻</b><button id="prevDay">‹ 前一天</button><input id="datePicker" type="date" aria-label="选择日期"><button id="nextDay">后一天 ›</button></section><div id="dispatchState" role="status" class="muted"></div><nav class="tabs"><button class="active" data-cat="">全部</button><button data-cat="国际政治">国际政治</button><button data-cat="AI与科技">人工智能与科技</button><button data-cat="全球经济金融">全球经济金融</button><button data-cat="社会与突发">社会与突发</button><button data-cat="reports">采集记录</button></nav><section id="content"><div class="empty">加载中…</div></section></main><script>
const box=document.querySelector('#content'),status=document.querySelector('#status'),picker=document.querySelector('#datePicker'),dateTitle=document.querySelector('#dateTitle'),prev=document.querySelector('#prevDay'),next=document.querySelector('#nextDay');let cat='',selectedDate=beijingToday();function beijingToday(){const p=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date()).reduce((a,x)=>(a[x.type]=x.value,a),{});return p.year+'-'+p.month+'-'+p.day}function today(){return beijingToday()}function showDate(){dateTitle.textContent=selectedDate+'（北京时间）';picker.value=selectedDate;next.disabled=selectedDate>=today()}function shiftDate(n){const d=new Date(selectedDate+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);selectedDate=d.toISOString().slice(0,10);showDate();load()}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
let sequence=0;
const formatter=new Intl.DateTimeFormat('zh-CN',{dateStyle:'long',timeStyle:'short',timeZone:'Asia/Shanghai'});
function date(value){const d=new Date(value);return value && Number.isFinite(d.getTime())?formatter.format(d):'时间未知'}
function safeHref(u){return new RegExp('^https?://','i').test(u||'')?u:''}
function pulseCount(x){const c=x.community||{};return (c.hn?.length||0)+(c.reddit?.length||0)+(x.polymarket?1:0)}
function renderPulse(data){
 const parts=[];
 if(data.polymarket){const p=data.polymarket,l=safeHref(p.url);parts.push('<h3>Polymarket 预测风向</h3><p>'+esc(p.event_title)+' · '+esc(p.outcome)+' '+esc(p.probability)+'%'+(p.volume_text?' · '+esc(p.volume_text):'')+(l?' <a target="_blank" rel="noopener noreferrer" href="'+esc(l)+'">查看盘口 ↗</a>':'')+'</p>');}
 const c=data.community||{};
 if(c.hn?.length){parts.push('<h3>Hacker News 社区讨论</h3><ul>'+c.hn.map(h=>{const d=safeHref(h.discussion_url);const label=h.title?esc(h.title):'讨论摘录';const pts=h.points>0?' · '+esc(h.points)+'分':'';const cm=h.num_comments>0?' · '+esc(h.num_comments)+'评':'';const comments=(h.comments||[]).map(x=>esc(x.text||x)).join('<br>');const body=comments||(h.text?esc(h.text):'');return '<li>'+label+pts+cm+(d?' <a target="_blank" rel="noopener noreferrer" href="'+esc(d)+'">讨论 ↗</a>':'')+(body?'<br><span class="muted">'+body+'</span>':'')+'</li>'}).join('')+'</ul>');}
 else if(data.source_status?.hn==='unavailable')parts.push('<p class="muted">HN 讨论暂不可用（接口限流或超时）。</p>');
 if(c.reddit?.length){parts.push('<h3>Reddit 社区热议</h3><ul>'+c.reddit.map(r=>{const u=safeHref(r.url);return '<li>r/'+esc(r.subreddit)+' · '+esc(r.title)+(r.score!=null?' · '+esc(r.score)+'赞':'')+(r.num_comments!=null?' · '+esc(r.num_comments)+'评':'')+(u?' <a target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">帖子 ↗</a>':'')+'</li>'}).join('')+'</ul>');}
 else if(data.source_status?.reddit==='unavailable')parts.push('<p class="muted">Reddit 讨论暂不可用。</p>');
 return parts.join('')||'<p class="muted">暂无相关社区或市场脉络。</p>';
}
const pulseInflight=new Map();
async function togglePulse(btn,fp){
 const drawer=btn.nextElementSibling;
 if(drawer.dataset.open==='1'){drawer.hidden=true;drawer.dataset.open='0';return;}
 drawer.hidden=false;drawer.dataset.open='1';
 if(drawer.dataset.loaded==='1')return;
 if(pulseInflight.has(fp))return;
 drawer.innerHTML='<p class="pulse-loading">正在加载社区与市场脉络…</p>';
 pulseInflight.set(fp,true);
 try{
  const response=await fetch('/api/pulse?fingerprint='+encodeURIComponent(fp),{cache:'no-store'});
  const data=await response.json();
  if(!response.ok)throw Error(data.error||'failed');
  drawer.innerHTML=renderPulse(data);
  drawer.dataset.loaded='1';
 }catch{drawer.innerHTML='<p class="muted">暂时无法加载脉络，请稍后重试。</p>';}
 finally{pulseInflight.delete(fp);}
}
async function load(){
 const id=++sequence,report=cat==='reports';
 try{
  const params=new URLSearchParams({date:selectedDate});if(cat&&!report)params.set('category',cat);const response=await fetch((report?'/api/reports':'/api/news')+'?'+params.toString(),{cache:'no-store'});
  if(!response.ok)throw Error();
  const data=await response.json();
  if(id!==sequence)return;
  status.textContent='按日期归档 · 北京时间 UTC+8';
  box.innerHTML=data.items.map(x=>{
   if(report)return '<article class="report"><b>'+date(x.run_at)+'</b><p>本轮收录 '+esc(x.new_count)+' 条新条目</p><div class="meta">候选 '+esc(x.candidate_count)+' · 来源错误 '+esc(x.source_error_count)+'</div></article>';
   const title=esc(x.title),safe=/^https?:/i.test(x.url);
   const image=x.image_url && x.image_url.startsWith('https://')?'<img class="photo" loading="lazy" referrerpolicy="no-referrer" alt="报道配图" src="'+esc(x.image_url)+'" onerror="this.hidden=true">':'';
   const text=x.reading_text||x.summary||'';
   const link=safe?'<a class="more" target="_blank" rel="noopener noreferrer" href="'+esc(x.url)+'">'+(text && !x.short_body?'更多 · 阅读原文':'查看原文')+' ↗</a>':'';
   let meta='';
   if(x.hn_meta)meta='<div class="hnmeta">Hacker News · '+esc(x.hn_meta.points)+'分 · '+esc(x.hn_meta.num_comments)+'评</div>';
   else if(x.source_name==='Hacker News'&&x.hn_meta)meta='';
   let pm='';
   if(x.polymarket){const p=x.polymarket,u=safeHref(p.url);pm='<div class="pmcap">预测市场 · '+esc(p.outcome)+' '+esc(p.probability)+'% · '+esc(p.event_title||p.question||'')+(u?' <a target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">↗</a>':'')+'</div>';}
   const pc=pulseCount(x);
   const pulse='<button type="button" class="pulse-btn" data-fp="'+esc(x.fingerprint)+'">社区与市场脉络'+(pc?' ('+pc+')':'')+'</button><div class="pulse-drawer" hidden></div>';
   const rel=x.related_sources||[];
   const multi=rel.length?'<div class="multi-src">多源报道 · 共 '+esc(x.source_count||1+rel.length)+' 家</div>':'';
   const related=rel.length?'<details class="related-sources"><summary>同题报道（另有 '+esc(rel.length)+' 家媒体）</summary><ul>'+rel.map(r=>{const u=safeHref(r.url);return '<li>'+esc(r.source_name)+' · '+esc(r.title)+(u?' <a target="_blank" rel="noopener noreferrer" href="'+esc(u)+'">原文 ↗</a>':'')+'</li>'}).join('')+'</ul></details>':'';
   const footerSources=rel.length?multi+' · '+esc(x.source_name)+(rel.length?('、'+rel.map(r=>esc(r.source_name)).join('、')):''):esc(x.source_name);
   return '<article class="item"><header><span class="tag">'+esc(x.category==='AI与科技'?'人工智能与科技':x.category)+'</span><time>'+date(x.published_at||x.collected_at)+'</time></header>'+multi+'<h2>'+title+'</h2>'+pm+meta+image+(text?'<p class="summary">'+esc(text)+'</p>':'<p class="muted">暂未取得原文内容，可打开来源网站查看。</p>')+related+pulse+'<footer><span>'+footerSources+' · 待核实</span>'+link+'</footer></article>';
  }).join('')||'<div class="empty">暂无记录，等待下一轮采集。</div>';
  box.querySelectorAll('.pulse-btn').forEach(b=>b.onclick=()=>togglePulse(b,b.dataset.fp));
 }catch{if(id===sequence){status.textContent='读取失败';box.innerHTML='<div class="empty">暂时无法读取数据，请稍后刷新。</div>'}}
}
const trigger=document.querySelector('#collect'),notice=document.querySelector('#dispatchState');
trigger.onclick=async()=>{
 trigger.disabled=true;notice.textContent='正在提交采集任务…';
 const workflow='https://github.com/jackiet512/global-news-monitor/actions/workflows/collect.yml';
 try{
  const response=await fetch('/api/collect',{method:'POST'});
  const detail=await response.json();
  if(response.status===429){notice.textContent='最近十分钟内已有人发起采集，请查看采集记录。';return}
  if(!response.ok)throw Error();
  notice.textContent='已提交采集任务。';
  if(detail.run_id){
   for(let i=0;i<64;i++){
    await new Promise(resolve=>setTimeout(resolve,10000));
    const r=await fetch('https://api.github.com/repos/jackiet512/global-news-monitor/actions/runs/'+detail.run_id);
    if(!r.ok)break;
    const run=await r.json();
    if(run.status==='completed'){
     notice.textContent=run.conclusion==='success'?'采集完成，已更新列表。':'采集任务未成功，请查看运行记录。';
     await load();return;
    }
    notice.textContent=run.status==='in_progress'?'正在采集新闻…':'任务已排队…';
   }
  }
  notice.textContent='任务已提交，进度可在运行记录中查看。';
 }catch{notice.textContent='未能确认提交，请在运行记录中检查或手动启动。'}
 finally{
  const a=document.createElement('a');a.href=workflow;a.target='_blank';a.rel='noopener';a.textContent=' 查看运行记录';notice.append(a);trigger.disabled=false;
 }
};
document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-cat]').forEach(x=>x.classList.remove('active'));b.classList.add('active');cat=b.dataset.cat;load()});prev.onclick=()=>shiftDate(-1);next.onclick=()=>{if(selectedDate<today())shiftDate(1)};picker.onchange=()=>{if(picker.value&&picker.value<=today()){selectedDate=picker.value;showDate();load()}else showDate()};showDate();load();setInterval(load,60000);
</script></html>`;
