const V='ms-v96';
const SKIN_RE=/^\/skins\//;
self.addEventListener('install',e=>{self.skipWaiting();e.waitUntil(caches.open(V).then(c=>c.addAll(['/famkey.js','/famlang.js','/icon-192.png','/icon-512.png','/icon.svg','/skins/side-cut/skin.json','/skins/side-cut/skin.css','/skins/side-cut/icons.svg','/skins/side-cut/preview.svg','/skins/side-cut/textures/paper.svg','/skins/side-cut/fonts/ArchivoBlack-Regular.woff2','/skins/classic-deck/skin.json','/skins/classic-deck/skin.css','/skins/classic-deck/icons.svg','/skins/classic-deck/preview.svg','/skins/classic-deck/fonts/VT323-Regular.woff2','/skins/glass-stage/skin.json','/skins/glass-stage/skin.css','/skins/glass-stage/icons.svg','/skins/glass-stage/preview.svg','/skins/glass-stage/fonts/Outfit-Variable.woff2'])).catch(()=>{}))});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k.startsWith('ms-')&&k!=V).map(k=>caches.open(k).then(o=>o.match('/shell')).then(r=>r&&caches.open(V).then(n=>n.put('/shell',r))).then(()=>caches.delete(k))))).then(()=>self.clients.claim())));
async function ranged(r,req){const b=await r.blob(),rg=req.headers.get('range'),ct=r.headers.get('content-type')||'audio/mp4';
if(!rg)return new Response(b,{headers:{'Content-Type':ct,'Content-Length':String(b.size),'Accept-Ranges':'bytes'}});
const m=/bytes=(\d*)-(\d*)/.exec(rg)||[];let s=m[1]?+m[1]:0,en=m[2]?+m[2]:b.size-1;en=Math.min(en,b.size-1);
return new Response(b.slice(s,en+1),{status:206,headers:{'Content-Type':ct,'Content-Range':`bytes ${s}-${en}/${b.size}`,'Content-Length':String(en-s+1),'Accept-Ranges':'bytes'}})}
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(u.origin!=location.origin||e.request.method!='GET')return;
/* adult-viz-20261111: never cache the gated 18+ pack; always go to the network (server 404s unless the user flag is on). */
if(/^\/assets\/(dance|chars\/vrm|viz)\/adult\//.test(u.pathname)){e.respondWith(fetch(e.request));return}
if(u.pathname=='/audio'||u.pathname=='/stream'){const id=u.searchParams.get('id');e.respondWith(caches.open('off').then(c=>c.match('/off/'+id)).then(r=>r?ranged(r,e.request):fetch(e.request)));return}
if(u.pathname=='/art'){e.respondWith(caches.open('off').then(c=>c.match('/offart/'+u.searchParams.get('id'))).then(r=>r||fetch(e.request)));return}
if(/^\/icon(-\d+\.png|\.svg)$/.test(u.pathname)){e.respondWith(caches.match(e.request).then(r=>r||fetch(e.request)));return}
if(SKIN_RE.test(u.pathname)){e.respondWith(caches.open(V).then(async c=>{const hit=await c.match(e.request);if(hit)return hit;try{const r=await fetch(e.request);if(r.ok)c.put(e.request,r.clone());return r}catch(err){return hit||Response.error()}}));return}
if(u.pathname=='/manifest.webmanifest'){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(V).then(x=>x.put('/manifest',c))}return r}).catch(()=>caches.open(V).then(x=>x.match('/manifest'))));return}
if(u.pathname.startsWith('/vendor/')){e.respondWith(caches.open(V).then(async c=>{const hit=await c.match(e.request);if(hit)return hit;try{const r=await fetch(e.request);if(r.ok)c.put(e.request,r.clone());return r}catch(err){return Response.error()}}));return}
/* dancefix: byte-range requests (the dancer loader fetches models in parallel ranges) are answered from a cached copy
   by slicing, otherwise passed straight to the network (a 206 can't be cached). Assets are immutable (30-day cache), so a
   cache hit is no longer re-downloaded in the background on every load — that re-fetched 14-20 MB dancers each visit. */
if(u.pathname.startsWith('/assets/')&&!/\.js$/.test(u.pathname)){if(e.request.headers.get('range')){e.respondWith(caches.open(V).then(c=>c.match(u.pathname,{ignoreSearch:true,ignoreVary:true})).then(hit=>hit?ranged(hit,e.request):fetch(e.request)).catch(()=>fetch(e.request)));return}
e.respondWith(caches.open(V).then(async c=>{const hit=await c.match(e.request,{ignoreVary:true});const net=()=>fetch(e.request).then(r=>{if(r.status===200)c.put(e.request,r.clone()).catch(()=>{});return r}).catch(()=>null);if(hit){if(/\.json$/.test(u.pathname))e.waitUntil(net());return hit}return (await net())||Response.error()}));return}
if(u.pathname.startsWith('/assets/')){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(V).then(x=>x.put(e.request,c))}return r}).catch(()=>caches.open(V).then(x=>x.match(e.request)).then(r=>r||Response.error())));return}
if(u.pathname=='/game.js'){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(V).then(x=>x.put('/game.js',c))}return r}).catch(()=>caches.open(V).then(x=>x.match('/game.js')).then(r=>r||Response.error())));return}
if(e.request.mode=='navigate'&&u.pathname=='/listen'){e.respondWith(fetch(e.request));return}
if(e.request.mode=='navigate'&&u.pathname=='/'){e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(V).then(x=>x.put('/shell',c))}return r}).catch(()=>caches.open(V).then(x=>x.match('/shell'))))}});

/* v72: read-only version responder for the in-app Diagnostics panel (answers only with the cache/build name and scope) */
/* v74: 'ms-claim' lets an already-active worker take control of a page loaded without it (hard reload / first visit). Read-only otherwise. */
self.addEventListener('message',e=>{const d=e.data||{};if(d.type==='ms-claim'){e.waitUntil(self.clients.claim().then(()=>{try{e.ports&&e.ports[0]&&e.ports[0].postMessage({type:'ms-claim',ok:true,v:V})}catch(_){}},err=>{try{e.ports&&e.ports[0]&&e.ports[0].postMessage({type:'ms-claim',ok:false,err:String(err&&err.name||'error')})}catch(_){}}));return}if(d.type!=='ms-version')return;const r={type:'ms-version',v:V,scope:(self.registration&&self.registration.scope)||''};try{if(e.ports&&e.ports[0])e.ports[0].postMessage(r);else if(e.source)e.source.postMessage(r)}catch(_){}});
