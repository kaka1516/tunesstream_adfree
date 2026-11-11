/* Music Stream Visuals (viz.js 1.0) — implements docs/VISUAL_DIRECTION.md (v1 spec). Own code, no deps.
   window.MSViz.init(canvas, analyser, opts) -> viz  (contract §8). Scenes built: marigold (S1), neonghat (S2, Canvas2D path).
   Avatar: pluggable slot (VRM/three-vrm, Live2D, …) — no built-in characters. */
(function(){'use strict';if(window.MSViz&&window.MSViz.init)return;
const clamp=(x,a,b)=>x<a?a:x>b?b:x,lerp=(a,b,t)=>a+(b-a)*t,TAU=Math.PI*2,D2R=Math.PI/180,now=()=>performance.now();
const median=a=>{const s=a.slice().sort((x,y)=>x-y);return s.length?s[s.length>>1]:0};
/* ======================= §1 Signal layer ======================= */
const KS_MAJ=[6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88],KS_MIN=[6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17];
const KEYN=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];
function corr(a,b){let ma=0,mb=0;for(let i=0;i<12;i++){ma+=a[i];mb+=b[i]}ma/=12;mb/=12;let n=0,da=0,db=0;for(let i=0;i<12;i++){const x=a[i]-ma,y=b[i]-mb;n+=x*y;da+=x*x;db+=y*y}return n/Math.sqrt(da*db+1e-9)}
class Signal{
 constructor(an){this.an=an;this.N=an.frequencyBinCount;this.f=new Uint8Array(this.N);this.td=new Uint8Array(an.fftSize);this.prev=new Uint8Array(this.N);
  this.hz=(an.context.sampleRate||48000)/an.fftSize;const b=h=>clamp(Math.round(h/this.hz),1,this.N-1);this.r={bass:[b(40),b(150)],mid:[b(150),b(2000)],high:[b(2000),b(10000)],fl1:[b(40),b(180)],fl2:[b(180),b(2000)]};
  this.pc=new Int8Array(this.N).fill(-1);for(let i=b(65);i<=b(2000);i++){const fr=i*this.hz,m=Math.round(12*Math.log2(fr/440))+69;this.pc[i]=((m%12)+12)%12}
  this.F={bass:0,mid:0,high:0,energy:0,centroid:0,onset:false,strength:0,bpm:96,conf:0,beatPhase:0,beat:false,beatN:0,bar:0,downbeat:false,drop:false,chroma:new Float32Array(12),key:'C',mode:'major',keyConf:0,idle:true,silent:true,t:0};
  this.mx={bass:.05,mid:.05,high:.05,energy:.02};this.reset(true)}
 reset(hard){this.flux=[];this.env=[];this.lastOnset=-1;this.bpms=[];this.lastAcf=0;this.lowConfT=now();if(hard){this.F.bpm=96;this.beatT=0;this.F.beatN=0}this.F.conf=0;this.eBeats=[];this.lastDrop=-99;this.beatBass=[0,0,0,0];this.dbOff=0}
 update(tMs,playing){const F=this.F,t=tMs/1000;F.onset=false;F.beat=false;F.drop=false;F.downbeat=false;
  if(!playing){for(const k of ['bass','mid','high','energy'])F[k]*=.92;F.strength=0;this._clock(t,true);F.t=t;return F}
  const f=this.f,an=this.an;an.getByteFrequencyData(f);an.getByteTimeDomainData(this.td);
  const band=([a,b])=>{let s=0;for(let i=a;i<=b;i++){s+=f[i]}return s/((b-a+1)*255)};
  const dec=.9993;for(const k of ['bass','mid','high']){const v=band(this.r[k]);this.mx[k]=Math.max(this.mx[k]*dec,v,.02);F[k]=lerp(F[k],clamp(v/this.mx[k],0,1),.2)}
  let s=0;for(let i=0;i<this.td.length;i+=2){const v=(this.td[i]-128)/128;s+=v*v}const rms=Math.sqrt(s/(this.td.length/2));this.mx.energy=Math.max(this.mx.energy*dec,rms,.02);F.energy=lerp(F.energy,clamp(rms/this.mx.energy,0,1),.2);F.silent=rms<.006;
  let num=0,den=0;for(let i=1;i<this.r.high[1];i++){num+=i*f[i];den+=f[i]}const cen=den?num/den*this.hz:200;F.centroid=lerp(F.centroid,clamp(Math.log(Math.max(200,cen)/200)/Math.log(25),0,1),.1);
  // spectral flux on 40–180 Hz + 180–2 kHz
  let fl=0;for(const [a,b] of [this.r.fl1,this.r.fl2]){let x=0;for(let i=a;i<=b;i++){const d=f[i]-this.prev[i];if(d>0)x+=d}fl+=x/((b-a+1)*255)}this.prev.set(f);
  this.flux.push([t,fl]);while(this.flux.length&&t-this.flux[0][0]>1)this.flux.shift();this.env.push([t,fl]);while(this.env.length&&t-this.env[0][0]>8)this.env.shift();
  const thr=median(this.flux.map(x=>x[1]))*1.5+.02;if(fl>thr&&t-this.lastOnset>.12&&!F.silent){F.onset=true;F.strength=clamp((fl-thr)/(thr+.02),0,1);this.lastOnset=t;this._pll(t)}else F.strength*=.85;
  if(t-this.lastAcf>.5&&this.env.length>200){this.lastAcf=t;this._acf(t)}
  // chroma (8 s EMA) -> key
  const ch=new Float32Array(12);for(let i=0;i<this.N;i++){const p=this.pc[i];if(p>=0)ch[p]+=f[i]*f[i]}let cs=0;for(let i=0;i<12;i++)cs+=ch[i];if(cs>0)for(let i=0;i<12;i++)F.chroma[i]=lerp(F.chroma[i],ch[i]/cs,.004);
  this._clock(t,false);F.t=t;return F}
 _acf(t){const env=this.env,fs=50,n=400,t0=t-8,x=new Float32Array(n);let j=0;for(let i=0;i<n;i++){const ti=t0+i/fs;while(j<env.length-1&&env[j+1][0]<=ti)j++;x[i]=env[j]?env[j][1]:0}
  let m=0;for(const v of x)m+=v;m/=n;for(let i=0;i<n;i++)x[i]-=m;const lo=Math.floor(60*fs/180),hi=Math.ceil(60*fs/60),ac=[];let best=-1,bl=0,sum=0,cnt=0;
  for(let L=lo;L<=hi;L++){let s=0;for(let i=L;i<n;i++)s+=x[i]*x[i-L];ac.push(s);if(s>best){best=s;bl=L}if(s>0){sum+=s;cnt++}}
  if(best<=0)return;const mean=sum/Math.max(1,cnt),conf=clamp((best/(mean+1e-9)-1)/2,0,1);let bpm=60*fs/bl;while(bpm<70)bpm*=2;while(bpm>140)bpm/=2;
  this.bpms.push(bpm);if(this.bpms.length>5)this.bpms.shift();const F=this.F;F.bpm=median(this.bpms);F.conf=lerp(F.conf,conf,.4)}
 _pll(t){if(!this.beatT)return;const P=60/this.F.bpm,el=(t-this.beatT)/P,fr=el-Math.round(el);if(Math.abs(fr*P)<.08)this.beatT+=fr*P*.1}
 _clock(t,paused){const F=this.F;if(F.conf<.3){if(now()-this.lowConfT>4000)F.idle=true}else{this.lowConfT=now();F.idle=false}if(F.silent&&!paused)F.idle=true;
  const bpm=F.idle?96:F.bpm,P=60/bpm;if(!this.beatT)this.beatT=t;if(paused){this.beatT+=0;return}let el=(t-this.beatT)/P;if(el>=1){const k=Math.floor(el);this.beatT+=k*P;F.beatN+=k;F.beat=true;el-=k;this._onBeat(t)}F.beatPhase=clamp(el,0,1)}
 _onBeat(t){const F=this.F;const i=F.beatN%4;this.beatBass[i]=lerp(this.beatBass[i],F.bass,.3);let bi=0;for(let k=1;k<4;k++)if(this.beatBass[k]>this.beatBass[bi])bi=k;this.dbOff=bi;F.bar=((F.beatN-bi)%4+4)%4;F.downbeat=F.bar===0;
  this.eBeats.push(F.energy);if(this.eBeats.length>8)this.eBeats.shift();const prev=this.eBeats.slice(-6,-1);if(prev.length>=5&&prev.slice(0,4).every(e=>e<.4)&&F.energy-prev[prev.length-1]>.35&&F.beatN-this.lastDrop>16){F.drop=true;this.lastDrop=F.beatN}
  if(F.beatN%8===0){let best=-2,b2=-2,bk=0,bm='major';for(let r=0;r<12;r++){const rot=Array.from({length:12},(_,i)=>F.chroma[(i+r)%12]);const a=corr(rot,KS_MAJ),b=corr(rot,KS_MIN);for(const [v,md] of [[a,'major'],[b,'minor']]){if(v>best){b2=best;best=v;bk=r;bm=md}else if(v>b2)b2=v}}F.key=KEYN[bk];F.mode=bm;F.keyRoot=bk;F.keyConf=clamp((best-b2)*5+(best-.5),0,1)}}
}
/* ======================= mood + style classifier (heuristic) ======================= */
class Mood{constructor(){this.style='hollywood';this.mood='calm';this.cand=null;this.agree=0;this.last=0;this.kw={};this.onsets=[]}
 setTrack(m){const s=((m.title||'')+' '+(m.channel||'')+' '+(m.lang||'')).toLowerCase(),raw=(m.title||'')+(m.channel||'');
  this.style=/[\u0C00-\u0C7F]/.test(raw)||/telugu|tollywood/.test(s)?'tollywood':/[\u0B80-\u0BFF]/.test(raw)||/tamil|kollywood|kuthu/.test(s)?'kollywood':'hollywood';
  this.kw={dev:/bhakti|stotram|aarti|bhajan|mantra|devotional|keerthana|suprabhatam/.test(s),rom:/love|prema|kadhal|manasu|heart/.test(s),sad:/sad|alone|pain|soga|baadha/.test(s)};this.mood='calm';this.cand=null;this.agree=0;this.onsets=[]}
 update(F){const t=F.t;if(F.onset)this.onsets.push(t);while(this.onsets.length&&t-this.onsets[0]>4)this.onsets.shift();if(t-this.last<2)return this.mood;this.last=t;
  const dens=this.onsets.length/4,b=F.idle?90:F.bpm,e=F.energy;let m;
  if(this.kw.dev||(e<.3&&F.centroid<.35))m='devotional';else if((b>=115&&e>=.55)||dens>=2.5)m='energetic';else if((b>=70&&b<=110&&F.mid>F.bass)||this.kw.rom)m='romantic';else if((b<90&&e<.35&&F.centroid<.45)||this.kw.sad)m='sad';else m=e<.45?'calm':'energetic';
  if(m===this.cand)this.agree++;else{this.cand=m;this.agree=1}if(this.agree>=2)this.mood=m;return this.mood}}
/* ======================= palette (§2 rule; OKLab k-means) ======================= */
const toLin=c=>{c/=255;return c<=.04045?c/12.92:Math.pow((c+.055)/1.055,2.4)},toS=c=>{c=c<=.0031308?12.92*c:1.055*Math.pow(c,1/2.4)-.055;return clamp(Math.round(c*255),0,255)};
function rgb2lab([r,g,b]){r=toLin(r);g=toLin(g);b=toLin(b);const l=Math.cbrt(.4122214708*r+.5363325363*g+.0514459929*b),m=Math.cbrt(.2119034982*r+.6806995451*g+.1073969566*b),s=Math.cbrt(.0883024619*r+.2817188376*g+.6299787005*b);
 return [.2104542553*l+.793617785*m-.0040720468*s,1.9779984951*l-2.428592205*m+.4505937099*s,.0259040371*l+.7827717662*m-.808675766*s]}
function lab2rgb([L,a,b]){const l=(L+.3963377774*a+.2158037573*b)**3,m=(L-.1055613458*a-.0638541728*b)**3,s=(L-.0894841775*a-1.291485548*b)**3;return [toS(4.0767416621*l-3.3077115913*m+.2309699292*s),toS(-1.2684380046*l+2.6097574011*m-.3413193965*s),toS(-.0041960863*l-.7034186147*m+1.707614701*s)]}
const lch=([L,a,b])=>[L,Math.hypot(a,b),Math.atan2(b,a)],fromLch=([L,C,h])=>[L,C*Math.cos(h),C*Math.sin(h)];
const hex=c=>'#'+c.map(x=>x.toString(16).padStart(2,'0')).join(''),parseCol=s=>{s=(s||'').trim();if(s[0]==='#'){let h=s.slice(1);if(h.length===3)h=h.split('').map(x=>x+x).join('');const n=parseInt(h.slice(0,6),16);return [n>>16&255,n>>8&255,n&255]}const m=s.match(/[\d.]+/g);return m&&m.length>=3?m.slice(0,3).map(Number):null};
const lum=c=>{const [r,g,b]=c.map(toLin);return .2126*r+.7152*g+.0722*b},contrast=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
function guard(fg,bg,min){let L=lch(rgb2lab(fg)),i=0;const up=lum(bg)<.2;while(contrast(lab2rgb(fromLch(L)),bg)<min&&i++<14)L[0]=clamp(L[0]+(up?.05:-.05),0,1);return lab2rgb(fromLch(L))}
function paletteFromImage(img,fb){try{if(!img||!img.complete||!img.naturalWidth)return fb;const c=document.createElement('canvas');c.width=c.height=32;const g=c.getContext('2d',{willReadFrequently:true});g.drawImage(img,0,0,32,32);const d=g.getImageData(0,0,32,32).data;
  const px=[];for(let i=0;i<d.length;i+=4)px.push(rgb2lab([d[i],d[i+1],d[i+2]]));px.sort((a,b)=>a[0]-b[0]);let C=[0,1,2,3,4].map(k=>px[Math.floor((k+.5)/5*px.length)].slice()),asg=new Int8Array(px.length);
  for(let it=0;it<8;it++){const S=C.map(()=>[0,0,0,0]);px.forEach((p,i)=>{let bi=0,bd=1e9;C.forEach((c,k)=>{const dd=(p[0]-c[0])**2+(p[1]-c[1])**2+(p[2]-c[2])**2;if(dd<bd){bd=dd;bi=k}});asg[i]=bi;const s=S[bi];s[0]+=p[0];s[1]+=p[1];s[2]+=p[2];s[3]++});S.forEach((s,k)=>{if(s[3])C[k]=[s[0]/s[3],s[1]/s[3],s[2]/s[3]]});C.forEach((c,k)=>c.n=S[k][3])}
  const cl=C.map(c=>({lab:c,n:c.n||0,lc:lch(c)}));const bgc=cl.filter(c=>c.n>20).sort((a,b)=>a.lab[0]-b.lab[0])[0]||cl[0];let bL=lch(bgc.lab);bL[0]=Math.min(bL[0],.18);
  const acc=cl.filter(c=>c.lc[1]>=.03).sort((a,b)=>b.n*b.lc[1]-a.n*a.lc[1]);if(!acc.length)return fb;const P=acc[0].lc;let S2=acc.find(c=>Math.abs(((c.lc[2]-P[2])*180/Math.PI+540)%360-180)>=40);const sec=S2?S2.lc:[P[0],P[1],P[2]+150*D2R];
  const bg=lab2rgb(fromLch(bL)),prim=guard(lab2rgb(fromLch([Math.max(P[0],.55),Math.max(P[1],.1),P[2]])),bg,3),secd=guard(lab2rgb(fromLch([Math.max(sec[0],.55),Math.max(sec[1],.08),sec[2]])),bg,3),glow=guard(lab2rgb(fromLch([.75,P[1]*1.2,P[2]])),bg,3);
  return {bg:hex(bg),primary:hex(prim),secondary:hex(secd),glow:hex(glow),src:'art'}}catch(e){return fb}}
function mixHex(a,b,t){const A=parseCol(a)||[0,0,0],B=parseCol(b)||[0,0,0];return hex(A.map((x,i)=>Math.round(lerp(x,B[i],t))))}
/* ======================= §3 Avatar slot (pluggable; no built-in characters) =======================
 A renderer (VRM via three-vrm, Live2D via pixi-live2d-display, sprite sheet, …) registers itself:
   MSViz.registerAvatar(id,{label, factory(host)->adapter|Promise<adapter>})
 host = {container (absolutely-positioned layer over the stage canvas, pointer-events:none), canvas, audioCtx, phone, dpr, dprCap, reducedMotion, box}
 adapter = {mode:'overlay'|'2d', update(frame), draw?(g,w,h,boxPx), trigger?(kind,info), hitTest?(x,y), resize?(cssW,cssH,dpr),
            setPalette?(pal), setVisible?(b), setQuality?(tier), dispose?()}
 frame (AvatarFrame) = {t,dt,bpm,conf,idle,beat,beatN,beatPhase,bar,downbeat,onset,strength,drop,energy,bass,mid,high,centroid,
            mood,style,key,intensity,reducedMotion,pointer:{x,y,active},box:{x,y,w,h},tier}
 update() runs synchronously inside the stage frame so its cost counts against the §6 budget (overlay renderers should render there, not in their own rAF).
 See docs/AVATAR_SLOT.md. */
const AVATARS=new Map();
function registerAvatar(id,def){if(!id||!def||typeof def.factory!=='function')throw new Error('registerAvatar(id,{label,factory})');AVATARS.set(id,Object.assign({label:id},def));try{window.dispatchEvent(new CustomEvent('msviz:avatars'))}catch(e){}return id}
function listAvatars(){return [...AVATARS.entries()].map(([id,d])=>({id,label:d.label}))}
/* ======================= particles (shared pool; caps §6) ======================= */
class Pool{constructor(){this.p=[];this.cap=600}
 add(o){if(this.p.length>=this.cap)this.p.shift();this.p.push(o)}
 step(g,dt,w,h,dpr){const k=dt/16.7;for(let i=this.p.length-1;i>=0;i--){const q=this.p[i];q.life-=q.decay*k;if(q.life<=0||q.y>h+40){this.p.splice(i,1);continue}q.vx*=Math.pow(q.drag||.99,k);q.vy=q.vy*Math.pow(q.drag||.99,k)+(q.grav||0)*k;q.x+=q.vx*k;q.y+=q.vy*k;q.rot=(q.rot||0)+(q.vr||0)*k;
   g.globalAlpha=clamp(q.life*1.6,0,1);g.fillStyle=q.c;if(q.shape==='petal'){g.save();g.translate(q.x,q.y);g.rotate(q.rot);g.beginPath();g.ellipse(0,0,q.s*dpr,q.s*.48*dpr,0,0,TAU);g.fill();g.restore()}
   else if(q.shape==='rect'){g.save();g.translate(q.x,q.y);g.rotate(q.rot);g.fillRect(-q.s*dpr/2,-q.s*.35*dpr,q.s*dpr,q.s*.7*dpr);g.restore()}else{g.beginPath();g.arc(q.x,q.y,q.s*dpr,0,TAU);g.fill()}}g.globalAlpha=1}}
/* ======================= §2 Scenes ======================= */
const MARIGOLD=['#ff9f1c','#ffbf1f','#ff6b1a','#ffd23f'];
const SCENES={
 marigold:{name:'Marigold Burst',
  frame(V,g,w,h,F,dt){const pal=V.pal,dpr=V.dpr,k=dt/16.7,S=V.st.marigold||(V.st.marigold={rot:0,rotT:0,ring:null,ringKey:'',wind:0});
   const bg=g.createLinearGradient(0,0,0,h);bg.addColorStop(0,pal.bg);bg.addColorStop(.7,mixHex(pal.bg,pal.primary,.22));bg.addColorStop(1,mixHex(pal.bg,'#000000',.4));g.fillStyle=bg;g.fillRect(0,0,w,h);
   const fy=h*.8,R=Math.min(w,h*1.6)*.28;const rk=pal.primary+pal.secondary+pal.glow+Math.round(R);if(S.ringKey!==rk){S.ring=rangoli(R*1.15,pal,dpr);S.ringKey=rk}
   if(F.downbeat&&!V.rm)S.rotT+=TAU/16;S.rot=lerp(S.rot,S.rotT,.08*k);const sc=1+.08*F.bass*V.amp;g.save();g.translate(w/2+V.bendX*w*.1,fy);g.scale(1,.32+V.bendY*.1);g.rotate(S.rot);g.scale(sc,sc);g.globalAlpha=.9;g.drawImage(S.ring,-S.ring.width/2,-S.ring.height/2);g.restore();g.globalAlpha=1;
   // glow behind stage
   const gl=g.createRadialGradient(w/2,fy,0,w/2,fy,R*1.4);gl.addColorStop(0,pal.glow);gl.addColorStop(1,'transparent');g.globalCompositeOperation='lighter';g.globalAlpha=.12+.18*F.energy*V.amp;g.fillStyle=gl;g.fillRect(0,0,w,h);g.globalAlpha=1;g.globalCompositeOperation='source-over';
   if(V.rm)return;const wind=V.pointer.active?(V.pointer.x-.5)*2:0;S.wind=lerp(S.wind,wind,.05);
   const rate=(V.cap*.012)*(F.idle?.4:(F.bpm/120))*V.intens*k;S.acc=(S.acc||0)+rate;while(S.acc>=1){S.acc--;V.pool.add({x:Math.random()*w,y:-10,vx:S.wind*1.2*dpr,vy:(.6+Math.random()*1.2)*dpr*(F.idle?.6:F.bpm/100),grav:.004*dpr,drag:.995,life:1,decay:.0025,s:3+Math.random()*4,c:Math.random()<.75?MARIGOLD[(Math.random()*4)|0]:pal.secondary,shape:Math.random()<.8?'petal':'rect',rot:Math.random()*TAU,vr:(Math.random()-.5)*.12})}
   if(F.onset&&F.strength>.35)V.burst(.5+(Math.random()-.5)*.3,.8,'petal',Math.round(14*V.intens*(.5+F.strength)));if(F.drop)V.cannons();},
  burstKind:'petal'},
 neonghat:{name:'Neon Ghat Steps',
  frame(V,g,w,h,F,dt){const pal=V.pal,dpr=V.dpr,k=dt/16.7,S=V.st.neon||(V.st.neon={dip:0,flash:0,vx:.5});g.fillStyle=pal.bg;g.fillRect(0,0,w,h);
   const tvx=V.pointer.active?V.pointer.x:.5;S.vx=lerp(S.vx,tvx,.06*k);if(F.drop&&!V.rm){S.dip=1;S.flash=1}S.dip*=Math.pow(.96,k);S.flash=Math.max(0,S.flash-.06*k);
   const vx=w*(S.vx+V.bendX*.25),hz=h*(.36+V.bendY*.12+S.dip*.06),steps=Math.round(9*V.detail)+5,ph=V.rm?0:(F.beatPhase||0),glowW=(1.2+2.8*F.bass*V.amp)*dpr;
   const sky=g.createLinearGradient(0,0,0,hz);sky.addColorStop(0,mixHex(pal.bg,'#000000',.3));sky.addColorStop(1,mixHex(pal.bg,pal.secondary,.25));g.fillStyle=sky;g.fillRect(0,0,w,hz);
   // sun/moon disk at vanishing point
   g.globalCompositeOperation='lighter';const sd=g.createRadialGradient(vx,hz,0,vx,hz,h*.32);sd.addColorStop(0,pal.glow);sd.addColorStop(.25,mixHex(pal.glow,pal.bg,.6));sd.addColorStop(1,'transparent');g.globalAlpha=.55+.25*F.energy;g.fillStyle=sd;g.fillRect(0,0,w,h);g.globalAlpha=1;
   // terraces: each step = a horizontal tread + riser; z in (0,1], scrolls toward viewer once per beat
   g.lineCap='round';const lines=[];for(let i=0;i<steps;i++){const z=(i+1-ph)/steps,zz=Math.pow(z,1.8),y=hz+(h*1.02-hz)*zz,half=w*(.08+1.1*zz),rise=(h-hz)*.05*zz;lines.push([y,half,rise,z])}
   for(const [y,half,rise,z] of lines){const a=clamp(z*1.3,0,1);g.strokeStyle=pal.primary;g.globalAlpha=a*.35;g.lineWidth=glowW*3*z+1;g.beginPath();g.moveTo(vx-half,y);g.lineTo(vx+half,y);g.stroke();g.strokeStyle=pal.glow;g.globalAlpha=a;g.lineWidth=Math.max(1,glowW*z);g.beginPath();g.moveTo(vx-half,y);g.lineTo(vx+half,y);g.moveTo(vx-half,y);g.lineTo(vx-half,y-rise);g.moveTo(vx+half,y);g.lineTo(vx+half,y-rise);g.stroke()}
   g.strokeStyle=pal.secondary;g.globalAlpha=.5;g.lineWidth=Math.max(1,glowW*.6);g.beginPath();for(const s of [-1,1]){g.moveTo(vx+s*w*.08,hz);g.lineTo(vx+s*w*1.2,h*1.02)}g.stroke();
   // water shimmer above the horizon band (highs)
   const nw=Math.round(6*V.detail)+3;g.strokeStyle=pal.secondary;for(let i=0;i<nw;i++){const yy=hz-6*dpr-i*5*dpr;g.globalAlpha=(.12+.4*F.high*V.amp)*(1-i/nw);g.lineWidth=dpr;g.beginPath();for(let x=0;x<=w;x+=12*dpr){const yv=yy+Math.sin(x*.02/dpr+F.t*3+i)*2*dpr*(1+F.high*3);x?g.lineTo(x,yv):g.moveTo(x,yv)}g.stroke()}
   g.globalAlpha=1;if(S.flash>0){g.fillStyle=pal.glow;g.globalAlpha=Math.min(.18,S.flash*.18);g.fillRect(0,0,w,h);g.globalAlpha=1}g.globalCompositeOperation='source-over';
   if(F.onset&&F.strength>.5&&!V.rm)V.burst(S.vx,.55,'ring',1);},burstKind:'ring'}};
function rangoli(R,pal,dpr){const S=Math.ceil(R*2.2),c=document.createElement('canvas');c.width=c.height=S;const g=c.getContext('2d');g.translate(S/2,S/2);const cols=[pal.primary,pal.secondary,pal.glow,'#ff9f1c'];
 for(let ring=0;ring<4;ring++){const r=R*(.35+ring*.2),n=8+ring*8;g.fillStyle=cols[ring%4];for(let i=0;i<n;i++){const a=i/n*TAU;g.save();g.rotate(a);g.translate(r,0);g.beginPath();g.ellipse(0,0,R*.07,R*.028,0,0,TAU);g.fill();g.restore()}
  g.strokeStyle=cols[(ring+1)%4];g.lineWidth=Math.max(1.5,R*.012);g.beginPath();g.arc(0,0,r+R*.07,0,TAU);g.stroke()}
 g.fillStyle=pal.glow;g.beginPath();g.arc(0,0,R*.18,0,TAU);g.fill();return c}
/* ======================= Toys (§7) ======================= */
const TOYS={
 cannons:{name:'Confetti cannons',tap(V,x,y){V.cannonAt(x,y,false)},long(V,x,y){V.cannons(true)}},
 stage:{name:'Stage lights',init(V){V.st.lights=[{x:.25,aim:.35},{x:.75,aim:.65}]},
  draw(V,g,w,h,F){const L=V.st.lights||(V.st.lights=[{x:.25,aim:.35},{x:.75,aim:.65}]),pal=V.pal;g.globalCompositeOperation='lighter';
   L.forEach((l,i)=>{if(!V.rm&&!l.held){l.aim=lerp(l.aim,clamp(l.x+Math.sin(F.t*.5+i*2+(F.bar||0)*.6)*.25,.05,.95),.02)}const sx=w*l.x,tx=w*l.aim,gr=g.createLinearGradient(sx,0,tx,h);gr.addColorStop(0,i?pal.secondary:pal.glow);gr.addColorStop(1,'transparent');g.globalAlpha=.22+.18*F.energy;g.fillStyle=gr;g.beginPath();g.moveTo(sx-w*.012,0);g.lineTo(sx+w*.012,0);g.lineTo(tx+w*.13,h);g.lineTo(tx-w*.13,h);g.closePath();g.fill()});
   g.globalAlpha=1;g.globalCompositeOperation='source-over';// crowd strip
   const n=Math.round(26*V.detail)+10,base=h*.985,jump=F.drop?1:0;V.st.crowdJ=Math.max(jump,(V.st.crowdJ||0)*.95);g.fillStyle='#000';g.globalAlpha=.85;g.beginPath();g.moveTo(0,h);
   for(let i=0;i<=n;i++){const x=i/n*w,ph=(F.beatPhase||0)*TAU+i*.7,wave=V.st.wave?Math.max(0,1-Math.abs(i/n-V.st.wave.x)*4)*V.st.wave.a:0,hh=h*(.06+.02*Math.sin(i*2.3))+(V.rm?0:(Math.max(0,Math.sin(ph))*h*.012+wave*h*.04+V.st.crowdJ*h*.03));g.lineTo(x-w/n*.3,base-hh);g.arc(x,base-hh-h*.012,h*.016,Math.PI,0);g.lineTo(x+w/n*.3,base-hh)}
   g.lineTo(w,h);g.closePath();g.fill();g.globalAlpha=1;if(V.st.wave){V.st.wave.a*=.95;if(V.st.wave.a<.02)V.st.wave=null}},
  down(V,x,y){const L=V.st.lights||[];if(y>.82){V.st.wave={x,a:1};return true}let best=null,bd=.2;L.forEach(l=>{const d=Math.abs(l.aim-x);if(d<bd){bd=d;best=l}});if(best){best.held=true;V.st.dragLight=best;return true}return false},
  drag(V,x,y){const l=V.st.dragLight;if(l)l.aim=clamp(x,0,1)},up(V){const l=V.st.dragLight;if(l)l.held=false;V.st.dragLight=null}},
 pads:{name:'Tap pads',draw(V,g,w,h,F){const P=V.padRects(w,h),pal=V.pal,labs=V.padLabels();g.font=`600 ${Math.round(12*V.dpr)}px system-ui`;g.textAlign='center';g.textBaseline='middle';
   P.forEach((r,i)=>{const hit=V.st.padHit&&V.st.padHit[i]||0;g.fillStyle=hit>.01?mixHex(pal.bg,pal.glow,.35+.6*hit):'rgba(0,0,0,.45)';g.strokeStyle=pal.primary;g.lineWidth=V.dpr*1.5;rr(g,r[0],r[1],r[2],r[3],10*V.dpr);g.fill();g.stroke();g.fillStyle='#fff';g.fillText(labs[i],r[0]+r[2]/2,r[1]+r[3]/2);if(V.st.padHit)V.st.padHit[i]*=.88})},
  down(V,x,y,w,h){const P=V.padRects(w,h);const px=x*w,py=y*h;const i=P.findIndex(r=>px>=r[0]&&px<=r[0]+r[2]&&py>=r[1]&&py<=r[1]+r[3]);if(i<0)return false;V.pad(i);return true}},
 paint:{name:'Beat paint',draw(V,g,w,h,F){const S=V.st.paint||(V.st.paint={strokes:[]}),pal=V.pal,beat=F.beat;g.lineCap='round';g.lineJoin='round';
   for(let si=S.strokes.length-1;si>=0;si--){const s=S.strokes[si];const age=(F.beatN-s.beat)/32;if(age>1&&!s.active){S.strokes.splice(si,1);continue}const a=clamp(1-age,0,1);if(s.pts.length<2)continue;
    g.strokeStyle=s.c;g.globalAlpha=a*(.55+.45*F.bass*V.amp);g.lineWidth=(4+10*F.bass*V.amp)*V.dpr;g.beginPath();g.moveTo(s.pts[0][0]*w,s.pts[0][1]*h);for(const p of s.pts)g.lineTo(p[0]*w,p[1]*h);g.stroke()}g.globalAlpha=1},
  down(V,x,y){const S=V.st.paint||(V.st.paint={strokes:[]});const hue=Math.round(V.sig.F.centroid*300);S.cur={pts:[[x,y]],c:`hsl(${hue},90%,62%)`,beat:V.sig.F.beatN,active:true};S.strokes.push(S.cur);let n=0;for(const s of S.strokes)n+=s.pts.length;while(n>2000&&S.strokes.length>1){n-=S.strokes.shift().pts.length}return true},
  drag(V,x,y){const S=V.st.paint;if(S&&S.cur)S.cur.pts.push([x,y])},up(V){const S=V.st.paint;if(S&&S.cur){S.cur.active=false;S.cur.beat=V.sig.F.beatN;S.cur=null}}}};
function rr(g,x,y,w,h,r){g.beginPath();g.moveTo(x+r,y);g.arcTo(x+w,y,x+w,y+h,r);g.arcTo(x+w,y+h,x,y+h,r);g.arcTo(x,y+h,x,y,r);g.arcTo(x,y,x+w,y,r);g.closePath()}
/* ======================= Viz controller ======================= */
function init(canvas,analyser,o){o=o||{};const phone=!!o.phone,V={canvas,g:canvas.getContext('2d'),phone,rm:!!o.reducedMotion,dpr:1,detail:1,amp:1,intens:1,cap:phone?180:600,pool:new Pool(),st:{},pointer:{x:.5,y:.5,active:false},bendX:0,bendY:0,zoom:1,
  sig:new Signal(analyser),mood:new Mood(),pal:{bg:'#120b18',primary:'#ffb627',secondary:'#e2384d',glow:'#ffd27a',src:'fallback'},palFrom:null,palT:1,palTo:null,scene:'auto',active:'marigold',prevSnap:null,xfade:0,avatar:null,avatarId:null,avatarErr:'',avBox:{x:.5,y:.9,w:.42,h:.6},avSel:false,avQ:null,avLastTap:-9,avLastSpecial:-99,avErrN:0,toy:null,
 tier:0,ft:[],ema:0,visible:true,raf:0,lastT:0,frameN:0,pausedSince:0,beatCbs:[],ptrCbs:[],intensity:'med',style:'auto',lastCalm:0,announceT:0,skinTokens:o.skinTokens||null};
 const dprCap=o.dprCap||(phone?1.25:2),budget=phone?10:6;V.pool.cap=V.cap;
 const TIERS=[{dpr:dprCap,pm:1,crew:3},{dpr:dprCap,pm:.5,crew:3},{dpr:Math.max(.75,dprCap-.25),pm:.5,crew:3},{dpr:Math.max(.75,dprCap-.5),pm:.5,crew:2},{dpr:.75,pm:.35,crew:2}];
 const audioEl=o.audioEl,toyCtx=o.audioCtx;let toyGain=null;
 function T(){return TIERS[V.tier]}
 function resize(){const L=T(),cw=Math.max(1,canvas.clientWidth),ch=Math.max(1,canvas.clientHeight),w=Math.round(cw*L.dpr),h=Math.round(ch*L.dpr);if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h}V.dpr=L.dpr;V.detail=L.pm;V.pool.cap=Math.round(V.cap*L.pm*({low:.5,med:1,high:1.3}[V.intensity]||1))}
 function fallbackPal(){const t=V.skinTokens&&V.skinTokens();if(t)return Object.assign({},V.pal,t,{src:'skin'});return V.pal}
 function setPalette(p){V.palFrom=Object.assign({},V.pal);V.palTo=p;V.palT=0}
 function stepPal(dt){if(V.palT>=1||!V.palTo)return;V.palT=Math.min(1,V.palT+dt/800);for(const k of ['bg','primary','secondary','glow'])V.pal[k]=mixHex(V.palFrom[k],V.palTo[k],V.palT);V.pal.src=V.palTo.src;if(V.palT>=1&&V.avatar&&V.avatar.setPalette)try{V.avatar.setPalette(Object.assign({},V.pal))}catch(e){}}
 // ---- scenes / auto ----
 function autoScene(){const m=V.mood.mood,st=V.style==='auto'?V.mood.style:V.style;if(m==='energetic')return st==='hollywood'?'neonghat':'marigold';return st==='hollywood'?'neonghat':'marigold'}
 function switchTo(id){if(id===V.active||!SCENES[id])return;try{const c=document.createElement('canvas');c.width=canvas.width;c.height=canvas.height;c.getContext('2d').drawImage(canvas,0,0);V.prevSnap=c;V.xfade=1}catch(e){}V.active=id;V.moodStable=now()}
 // ---- bursts / cannons ----
 V.burst=(x,y,kind,n)=>{if(V.rm){V.st.glow={x,y,a:1};return}const w=canvas.width,h=canvas.height,dpr=V.dpr,cols=[V.pal.primary,V.pal.secondary,V.pal.glow,...MARIGOLD];n=n||Math.round(22*V.intens);
  if(kind==='ring'){V.st.rings=(V.st.rings||[]);V.st.rings.push({x:x*w,y:y*h,a:1,c:V.pal.glow});if(V.st.rings.length>8)V.st.rings.shift();n=Math.round(n*.6)}
  for(let i=0;i<n;i++){const a=Math.random()*TAU,s=(1+Math.random()*4)*dpr;V.pool.add({x:x*w,y:y*h,vx:Math.cos(a)*s,vy:Math.sin(a)*s-2*dpr,grav:.08*dpr,drag:.97,life:1,decay:.012+Math.random()*.01,s:2+Math.random()*3,c:cols[(Math.random()*cols.length)|0],shape:kind==='petal'?'petal':(i%3?'dot':'rect'),rot:Math.random()*TAU,vr:(Math.random()-.5)*.3})}};
 V.cannonAt=(x,y,big)=>{if(V.rm){V.st.glow={x,y,a:1};return}const w=canvas.width,h=canvas.height,dpr=V.dpr,n=Math.round((big?90:40)*V.intens),cols=[V.pal.primary,V.pal.secondary,V.pal.glow,'#ffffff',...MARIGOLD],dir=x<.5?1:-1;
  for(let i=0;i<n;i++){const a=-Math.PI/2+dir*(.15+Math.random()*.45),s=(6+Math.random()*7)*dpr*(big?1.3:1);V.pool.add({x:x*w,y:h*clamp(y,.6,1),vx:Math.cos(a)*s,vy:Math.sin(a)*s,grav:.12*dpr,drag:.985,life:1,decay:.006+Math.random()*.006,s:2.5+Math.random()*3,c:cols[(Math.random()*cols.length)|0],shape:i%2?'rect':'petal',rot:Math.random()*TAU,vr:(Math.random()-.5)*.4})}toySound('pop')};
 V.cannons=(big)=>{V.cannonAt(.04,.98,big);V.cannonAt(.96,.98,big)};
 V.padRects=(w,h)=>{const cols=4,rows=2,pad=8*V.dpr,bw=Math.min((w-pad*5)/cols,140*V.dpr),bh=Math.max(64*V.dpr,Math.min(h*.14,90*V.dpr)),x0=(w-(bw*cols+pad*(cols-1)))/2,y0=h-bh*2-pad*2-16*V.dpr,r=[];for(let j=0;j<rows;j++)for(let i=0;i<cols;i++)r.push([x0+i*(bw+pad),y0+j*(bh+pad),bw,bh]);return r};
 const PENT=[0,2,4,7,9,12,14,16];V.padLabels=()=>{const F=V.sig.F,ok=F.keyConf>=.5;const root=ok?F.keyRoot||0:0,sc=ok?(F.mode==='minor'?[0,3,5,7,10,12,15,17]:[0,2,4,7,9,12,14,16]):PENT;return sc.map(s=>KEYN[(root+s)%12])};
 V.pad=i=>{V.st.padHit=V.st.padHit||new Array(8).fill(0);V.st.padHit[i]=1;const F=V.sig.F,ok=F.keyConf>=.5,root=ok?F.keyRoot||0:0,sc=ok?(F.mode==='minor'?[0,3,5,7,10,12,15,17]:[0,2,4,7,9,12,14,16]):PENT;toySound('key',261.63*Math.pow(2,(root+sc[i])/12))};
 function ensureToyAudio(){if(toyGain||!toyCtx)return toyGain;toyGain=toyCtx.createGain();toyGain.gain.value=Math.pow(10,-12/20);toyGain.connect(toyCtx.destination);return toyGain}
 let voices=0;function toySound(kind,freq){const ctx=toyCtx,gn=ensureToyAudio();if(!ctx||!gn||voices>=8)return;voices++;const t=ctx.currentTime,e=ctx.createGain();e.connect(gn);
  if(kind==='key'){const o1=ctx.createOscillator();o1.type='triangle';o1.frequency.value=freq;o1.connect(e);e.gain.setValueAtTime(0,t);e.gain.linearRampToValueAtTime(.5,t+.01);e.gain.exponentialRampToValueAtTime(.001,t+.6);o1.start(t);o1.stop(t+.62);o1.onended=()=>{voices--;e.disconnect()}}
  else{const b=ctx.createBuffer(1,ctx.sampleRate*.15,ctx.sampleRate),d=b.getChannelData(0);for(let i=0;i<d.length;i++)d[i]=(Math.random()*2-1)*Math.pow(1-i/d.length,3);const s=ctx.createBufferSource();s.buffer=b;const f=ctx.createBiquadFilter();f.type='bandpass';f.frequency.value=1800;s.connect(f).connect(e);e.gain.value=.4;s.start(t);s.onended=()=>{voices--;e.disconnect()}}}
 // ---- avatar slot ----
 let avLayer=null;
 function ensureLayer(){if(avLayer&&avLayer.isConnected)return avLayer;const par=canvas.parentNode;avLayer=document.createElement('div');avLayer.className='msv-avatar';avLayer.setAttribute('aria-hidden','true');
  avLayer.style.cssText='position:absolute;inset:0;pointer-events:none;overflow:hidden;z-index:1';if(par){if(getComputedStyle(par).position==='static')par.style.position='relative';canvas.nextSibling?par.insertBefore(avLayer,canvas.nextSibling):par.appendChild(avLayer)}return avLayer}
 function boxPx(w,h){const b=V.avBox;return {x:(b.x-b.w/2)*w,y:(b.y-b.h)*h,w:b.w*w,h:b.h*h}}
 async function setAvatar(id){const tok=(V.avTok=(V.avTok||0)+1);if(V.avatar){try{V.avatar.dispose&&V.avatar.dispose()}catch(e){}V.avatar=null}if(avLayer)avLayer.replaceChildren();V.avatarId=null;V.avatarErr='';V.avErrN=0;
  if(!id||id==='none')return true;const def=AVATARS.get(id);if(!def){V.avatarErr='unknown avatar '+id;return false}
  const saved=(V.avatarPos||{})[id];if(saved){V.avBox.x=saved[0];V.avBox.y=saved[1]}
  try{const host={container:ensureLayer(),canvas,audioCtx:o.audioCtx||null,phone,dpr:V.dpr,dprCap,reducedMotion:V.rm,box:V.avBox};const a=await def.factory(host);if(tok!==V.avTok){try{a&&a.dispose&&a.dispose()}catch(e){}return false}
   if(!a||typeof a.update!=='function')throw new Error('adapter must implement update(frame)');a.mode=a.mode||'2d';V.avatar=a;V.avatarId=id;try{resize();a.setPalette&&a.setPalette(Object.assign({},V.pal));a.resize&&a.resize(canvas.clientWidth,canvas.clientHeight,V.dpr);a.setQuality&&a.setQuality(V.tier)}catch(e){}try{V.visible=true;if(!V.raf)V.start()}catch(e){}announce((def.label||id)+' on stage');return true}
  catch(e){V.avatarErr=String(e&&e.message||e);console.warn('avatar',id,e);return false}}
 function avatarAt(x,y){if(!V.avatar)return false;try{if(V.avatar.hitTest)return !!V.avatar.hitTest(x,y)}catch(e){}const b=V.avBox;return x>b.x-b.w/2&&x<b.x+b.w/2&&y>b.y-b.h&&y<b.y}
 function avFrame(F,dt){const b=V.avBox;return {t:F.t,dt,bpm:F.idle?96:F.bpm,conf:F.conf,idle:F.idle,beat:F.beat,beatN:F.beatN,beatPhase:F.beatPhase,bar:F.bar,downbeat:F.downbeat,onset:F.onset,strength:F.strength,drop:F.drop,
  energy:F.energy,bass:F.bass,mid:F.mid,high:F.high,centroid:F.centroid,mood:V.mood.mood,style:V.style==='auto'?V.mood.style:V.style,key:F.key+(F.mode==='minor'?'m':''),intensity:V.rm?.15:V.amp,reducedMotion:V.rm,
  pointer:Object.assign({},V.pointer),box:{x:b.x,y:b.y,w:b.w,h:b.h},tier:V.tier}}
 /* ms-v75 stage probe: measures what the avatar ACTUALLY put on the visible stage (not an offscreen cache).
    2d adapters: box region of the visible canvas read just before and just after a.draw() in the same frame; a pixel
    counts as avatar if the draw changed it. overlay adapters (VRM): the visible overlay canvas itself (transparent bg). */
 function probeRect(b,w,h){const x=Math.max(0,Math.floor(b.x)),y=Math.max(0,Math.floor(b.y)),x2=Math.min(w,Math.ceil(b.x+b.w)),y2=Math.min(h,Math.ceil(b.y+b.h));return {x,y,w:Math.max(1,x2-x),h:Math.max(1,y2-y)}}
 function probeCapture(pq,a,g,w,h,pre,B0){try{let mask=null,col=null,n=0,boxN=0,stageN=Math.max(1,w*h),kind=a.mode,src=null;
   if(a.mode==='2d'){if(!pre){pq.res({ok:false,kind,reason:pq.err||'no readback'});return}const post=g.getImageData(B0.x,B0.y,B0.w,B0.h),A=pre.data,P=post.data,L=B0.w*B0.h;mask=new Uint8Array(L);col=new Uint8Array(L*3);boxN=L;
    for(let i=0,j=0;j<L;i+=4,j++){const d=Math.abs(A[i]-P[i])+Math.abs(A[i+1]-P[i+1])+Math.abs(A[i+2]-P[i+2]);if(d>24){mask[j]=1;n++}col[j*3]=P[i];col[j*3+1]=P[i+1];col[j*3+2]=P[i+2]}src=canvas}
   else{const oc=avLayer&&avLayer.querySelector('canvas');if(!oc||!oc.width||!oc.height){pq.res({ok:false,kind,reason:'no overlay canvas'});return}src=oc;
    const sw=Math.min(oc.width,480),sh=Math.max(1,Math.round(oc.height*sw/oc.width)),sc=document.createElement('canvas');sc.width=sw;sc.height=sh;const sx=sc.getContext('2d',{willReadFrequently:true});sx.drawImage(oc,0,0,sw,sh);
    const D=sx.getImageData(0,0,sw,sh).data,L=sw*sh;mask=new Uint8Array(L);col=new Uint8Array(L*3);boxN=0;stageN=L;const bb=V.avBox,bx0=(bb.x-bb.w/2)*sw,bx1=(bb.x+bb.w/2)*sw,by0=(bb.y-bb.h)*sh,by1=bb.y*sh;let inBox=0;
    for(let i=0,j=0;j<L;i+=4,j++){if(D[i+3]>20){mask[j]=1;n++;const x=j%sw,y=(j/sw)|0;if(x>=bx0&&x<bx1&&y>=by0&&y<by1)inBox++}col[j*3]=D[i];col[j*3+1]=D[i+1];col[j*3+2]=D[i+2]}
    boxN=Math.max(1,Math.round((bx1-bx0)*(by1-by0)));pq.inBox=inBox}
   const boxPx_=a.mode==='2d'?n:(pq.inBox||0);
   pq.res({ok:true,kind,avatarPx:n,boxPct:+(100*boxPx_/Math.max(1,boxN)).toFixed(2),stagePct:+(100*(a.mode==='2d'?n/stageN:n/stageN)).toFixed(2),mask,col,dims:a.mode==='2d'?[B0.w,B0.h]:[Math.sqrt(stageN)|0,0],src})}
  catch(e){pq.res({ok:false,kind:a.mode,reason:'probe error '+(e&&e.name||e)})}}
 function domVis(el){const out={el:el?(el.tagName.toLowerCase()+(el.id?'#'+el.id:'')+(el.className&&typeof el.className==='string'?'.'+el.className.split(/\s+/).filter(Boolean).join('.'):'')):'none'};if(!el){out.ok=false;return out}
  const r=el.getBoundingClientRect();out.rect=[Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height)];out.bitmap=[el.width||0,el.height||0];const issues=[];
  if(!el.isConnected)issues.push('detached');if(r.width<2||r.height<2)issues.push('zero-size');if(r.right<=0||r.bottom<=0||r.left>=innerWidth||r.top>=innerHeight)issues.push('offscreen');
  for(let n=el;n&&n.nodeType===1;n=n.parentElement){const cs=getComputedStyle(n);if(cs.display==='none')issues.push('display:none on '+(n.id||n.tagName.toLowerCase()));if(cs.visibility==='hidden')issues.push('visibility:hidden on '+(n.id||n.tagName.toLowerCase()));if(+cs.opacity<.05)issues.push('opacity '+cs.opacity+' on '+(n.id||n.tagName.toLowerCase()))}
  const cx=Math.min(innerWidth-1,Math.max(0,r.left+r.width*V.avBox.x)),cy=Math.min(innerHeight-1,Math.max(0,r.top+r.height*(V.avBox.y-V.avBox.h/2)));let top=null;try{top=document.elementFromPoint(cx,cy)}catch(e){}
  const stageEl=canvas.parentNode;out.topAtAvatar=top?(top.tagName.toLowerCase()+(top.id?'#'+top.id:'')):'none';if(top&&stageEl&&!stageEl.contains(top)&&!top.contains(stageEl))issues.push('covered by '+out.topAtAvatar);
  out.issues=issues;out.ok=!issues.length;return out}
 function probeOnce(timeout){return new Promise(res=>{const q={res:null};let done=false;const t=setTimeout(()=>{if(done)return;done=true;V.probeQ=(V.probeQ||[]).filter(x=>x!==q);res({ok:false,reason:'no avatar frame drawn within '+timeout+'ms (render loop stopped, stage hidden, or no avatar)'})},timeout);
  q.res=r=>{if(done)return;done=true;clearTimeout(t);res(r)};(V.probeQ=V.probeQ||[]).push(q);if(!V.raf)try{V.start()}catch(e){}})}
 async function probeAvatar(opts){opts=opts||{};const gap=opts.gapMs||700,to=opts.timeoutMs||4000;const base={build:'stage-probe r1',avatar:V.avatarId,mode:V.avatar?V.avatar.mode:null,avatarErr:V.avatarErr||'',running:!!V.raf,visibleFlag:V.visible,dpr:V.dpr,tier:V.tier,stage:[canvas.width,canvas.height]};
  if(!V.avatar){return Object.assign(base,{pass:false,reason:V.avatarErr?'avatar failed: '+V.avatarErr:'no avatar on stage'})}
  const a=await probeOnce(to);if(!a.ok)return Object.assign(base,{pass:false,reason:a.reason});await new Promise(r=>setTimeout(r,gap));const b=await probeOnce(to);if(!b.ok)return Object.assign(base,{pass:false,reason:'second sample: '+b.reason});
  let uni=0,xor=0,inter=0,cd=0;const L=Math.min(a.mask.length,b.mask.length);for(let j=0;j<L;j++){const x=a.mask[j],y=b.mask[j];if(x||y)uni++;if(x!==y)xor++;if(x&&y){inter++;cd+=Math.abs(a.col[j*3]-b.col[j*3])+Math.abs(a.col[j*3+1]-b.col[j*3+1])+Math.abs(a.col[j*3+2]-b.col[j*3+2])}}
  const motionPct=+(100*xor/Math.max(1,uni)).toFixed(2),colorDelta=+(inter?cd/(inter*3):0).toFixed(2),dom=domVis(a.src);
  const boxPct=Math.max(a.boxPct,b.boxPct),stagePct=Math.max(a.stagePct,b.stagePct),cov=boxPct>5,anim=motionPct>.5||colorDelta>2;
  return Object.assign(base,{kind:a.kind,boxPct,stagePct,motionPct,colorDelta,dom,coverageOk:cov,animOk:anim,pass:cov&&anim&&dom.ok,
   note:'boxPct = share of the avatar slot box covered by pixels the avatar actually drew on the VISIBLE '+(a.kind==='2d'?'stage canvas':'overlay canvas')+'; stagePct = share of the whole stage. motionPct/colorDelta compare two samples '+gap+'ms apart. pass needs boxPct>5, motion, and no DOM visibility issue. Read-only; a human must still look at the stage.'})}
 function stepAvatar(g,w,h,F,dt){const a=V.avatar;if(!a)return;if(a.setQuality&&V._tq!==V.tier){V._tq=V.tier;try{a.setQuality(V.tier)}catch(e){}}const cw=canvas.clientWidth,ch=canvas.clientHeight;if(a.resize&&(V._rw!==cw||V._rh!==ch||V._rd!==V.dpr)){V._rw=cw;V._rh=ch;V._rd=V.dpr;try{a.resize(cw,ch,V.dpr)}catch(e){}}const bp=beatPos();if(V.avQ&&bp>=V.avQ.at){const q=V.avQ;V.avQ=null;try{a.trigger&&a.trigger(q.kind,{beatN:F.beatN,bpm:F.bpm})}catch(e){}}
  const pq=V.probeQ&&V.probeQ.length?V.probeQ.shift():null;let pre=null,B0=null;
  try{a.update(avFrame(F,dt));if(a.mode==='2d'&&a.draw){g.setTransform(1,0,0,1,0,0);if(pq){B0=probeRect(boxPx(w,h),w,h);try{pre=g.getImageData(B0.x,B0.y,B0.w,B0.h)}catch(e){pq.err='readback '+(e&&e.name||e)}}a.draw(g,w,h,boxPx(w,h));g.setTransform(1,0,0,1,0,0)}V.avErrN=0;if(pq)probeCapture(pq,a,g,w,h,pre,B0)}
  catch(e){if(++V.avErrN>=3){V.avatarErr='disabled after errors: '+(e&&e.message||e);console.warn('avatar disabled',e);setAvatar(null)}}
  if(V.avSel){const B=boxPx(w,h);g.strokeStyle=V.pal.glow;g.lineWidth=2*V.dpr;g.setLineDash([6*V.dpr,5*V.dpr]);g.beginPath();g.ellipse(B.x+B.w/2,B.y+B.h,B.w*.3,B.w*.06,0,0,TAU);g.stroke();g.setLineDash([])}}
 function announce(t){if(now()-V.announceT<2000)return;V.announceT=now();o.announce&&o.announce(t)}
 function beatPos(){const F=V.sig.F;return F.beatN+F.beatPhase}
 V.trigger=(kind)=>{if(!V.avatar)return false;const bp=beatPos(),next=Math.floor(bp)+1,lbl=(AVATARS.get(V.avatarId)||{}).label||'Avatar';if(kind==='tap'||kind==='cheer'){if(bp-V.avLastTap<1)return false;V.avLastTap=bp;V.avQ={kind:'tap',at:V.rm?bp:next};announce(lbl+': cheer')}
  else{if(bp-V.avLastSpecial<16)return false;V.avLastSpecial=bp;V.avQ={kind:'special',at:V.rm?bp:next};announce(lbl+': special move')}
  if('vibrate' in navigator&&V.haptics&&!V.rm)try{navigator.vibrate(12)}catch(e){}V.burst(V.avBox.x,V.avBox.y-V.avBox.h*.6,'dot',10);return true};
 // ---- pointer (§5) ----
 const ptrs=new Map();let gest=null,lastTap={t:0,x:0,y:0},pinch0=0,zoom0=1,lpT=0;
 function rel(e){const r=canvas.getBoundingClientRect();return [(e.clientX-r.left)/r.width,(e.clientY-r.top)/r.height,r]}
 canvas.addEventListener('pointerdown',e=>{const [x,y,r]=rel(e);if(e.clientY>r.bottom-16||e.clientX<16||e.clientX>innerWidth-16)return;ptrs.set(e.pointerId,{x,y});if(ptrs.size>2)return;
  if(ptrs.size===2){const [a,b]=[...ptrs.values()];pinch0=Math.hypot(a.x-b.x,a.y-b.y);zoom0=V.zoom;gest={type:'pinch'};return}
  V.pointer={x,y,active:true};const toy=V.toy&&TOYS[V.toy];if(toy&&toy.down&&toy.down(V,x,y,canvas.width,canvas.height)){gest={type:'toy',id:e.pointerId,sx:x,sy:y,t:now()};return}
  const d=avatarAt(x,y);gest={type:d?'avatar':'stage',id:e.pointerId,sx:x,sy:y,t:now(),moved:false,vx:0,vy:0,lx:x,ly:y,lt:now()};clearTimeout(lpT);
  lpT=setTimeout(()=>{if(gest&&!gest.moved){if(gest.type==='avatar'){V.trigger('special');gest.done=true;emit('avatar-special',x,y)}else if(V.toy&&TOYS[V.toy].long){TOYS[V.toy].long(V,x,y);gest.done=true}}},500)});
 canvas.addEventListener('pointermove',e=>{const [x,y]=rel(e);V.pointer={x,y,active:true};V.lastMoveT=now();const p=ptrs.get(e.pointerId);if(p){p.x=x;p.y=y}if(!gest)return;
  if(gest.type==='pinch'&&ptrs.size===2){const [a,b]=[...ptrs.values()];V.zoom=clamp(zoom0*Math.hypot(a.x-b.x,a.y-b.y)/(pinch0||1),.9,1.3);return}
  if(gest.type==='toy'){const toy=TOYS[V.toy];toy&&toy.drag&&toy.drag(V,x,y);return}
  const dx=(x-gest.sx)*canvas.clientWidth,dy=(y-gest.sy)*canvas.clientHeight;if(!gest.moved&&Math.hypot(dx,dy)>8){gest.moved=true;clearTimeout(lpT);try{canvas.setPointerCapture(e.pointerId)}catch(_){}}
  if(!gest.moved)return;const t=now(),dt=Math.max(1,t-gest.lt);gest.vx=(x-gest.lx)/dt*1000;gest.vy=(y-gest.ly)/dt*1000;gest.lx=x;gest.ly=y;gest.lt=t;
  if(gest.type==='avatar'){V.avBox.x=clamp(x,.15,.85);V.avBox.y=clamp(y+V.avBox.h*.5,.62,.98)}
  else{V.bendX=clamp((x-gest.sx)*2,-1,1);V.bendY=clamp((y-gest.sy)*2,-1,1);V.bendT=now();emit('drag',x,y)}});
 const up=e=>{const [x,y]=rel(e);ptrs.delete(e.pointerId);clearTimeout(lpT);if(!gest)return;const g0=gest;if(g0.type==='pinch'){if(ptrs.size===0)gest=null;return}gest=null;
  if(g0.type==='toy'){const toy=TOYS[V.toy];toy&&toy.up&&toy.up(V);return}if(g0.done)return;
  if(g0.moved){if(g0.type==='avatar'){const dt=now()-g0.t,dx=(x-g0.sx)*canvas.clientWidth;if(Math.abs(dx)>60&&dt<300&&AVATARS.size>1){swapAvatar(dx>0?1:-1)}else{V.avatarPos=V.avatarPos||{};V.avatarPos[V.avatarId]=[+V.avBox.x.toFixed(3),+V.avBox.y.toFixed(3)];o.onSave&&o.onSave()}emit('avatar-move',x,y)}
   else{V.inertia={vx:clamp(g0.vx/400,-3,3),vy:clamp(g0.vy/400,-3,3)}}return}
  const dbl=now()-lastTap.t<320&&Math.hypot(x-lastTap.x,y-lastTap.y)<.06;lastTap={t:now(),x,y};
  if(g0.type==='avatar'){if(dbl){V.trigger('special');emit('avatar-special',x,y)}else{V.trigger('tap');emit('avatar-tap',x,y)}return}
  if(dbl){V.resetView();return}const toy=V.toy&&TOYS[V.toy];if(toy&&toy.tap){toy.tap(V,x,y);emit('tap',x,y);return}tapBurst(x,y);emit('tap',x,y)};
 canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',e=>{ptrs.delete(e.pointerId);gest=null;clearTimeout(lpT)});canvas.addEventListener('pointerleave',e=>{if(e.pointerType==='mouse'&&!gest)V.pointer.active=false});
 let tapQ=[];function tapBurst(x,y){const t=now();tapQ=tapQ.filter(q=>t-q<1000);if(tapQ.length>=5)return;tapQ.push(t);const F=V.sig.F,kind=(SCENES[V.active]||{}).burstKind||'dot';
  if(F.conf>=.5&&V.quantize!==false&&!F.idle){const P=60/F.bpm,el=F.beatPhase*8,wait=(Math.ceil(el+1e-3)-el)/8*P*1000;V.st.sched=(V.st.sched||[]);V.st.sched.push({at:t+wait,x,y,kind})}else V.burst(x,y,kind)}
 function swapAvatar(dir){const ids=[...AVATARS.keys()];if(ids.length<2||!V.avatarId)return;const n=ids[(ids.indexOf(V.avatarId)+dir+ids.length)%ids.length];setAvatar(n).then(ok=>{if(ok)o.onSwap&&o.onSwap(n)})}
 V.resetView=()=>{V.bendX=0;V.bendY=0;V.zoom=1;V.inertia=null};
 function emit(type,x,y,slot){for(const cb of V.ptrCbs)try{cb({type,x,y,slot})}catch(e){}}
 // keyboard (Space not captured)
 canvas.tabIndex=0;canvas.setAttribute('role','application');canvas.setAttribute('aria-label','Visualizer stage');
 canvas.addEventListener('keydown',e=>{const k=e.key;if(k===' ')return;const d=V.avSel&&V.avatar;let used=true;
  if(k==='b'||k==='B')tapBurst(.5,.6);else if(k==='1'){V.avSel=!!V.avatar&&!V.avSel}else if(k==='c'||k==='C')V.trigger('tap');else if(k==='s'||k==='S')V.trigger('special');
  else if(k==='0')V.resetView();else if(k==='v'||k==='V'){const ids=['auto','marigold','neonghat'];V.setScene(ids[(ids.indexOf(V.scene)+1)%ids.length])}else if(k==='Escape')V.avSel=false;else if(k==='f'||k==='F')V.cannons();
  else if(k.startsWith('Arrow')){const dx=k==='ArrowLeft'?-.03:k==='ArrowRight'?.03:0,dy=k==='ArrowUp'?-.03:k==='ArrowDown'?.03:0;if(d){V.avBox.x=clamp(V.avBox.x+dx,.15,.85);V.avBox.y=clamp(V.avBox.y+dy,.62,.98)}else{V.bendX=clamp(V.bendX+dx*3,-1,1);V.bendY=clamp(V.bendY+dy*3,-1,1);V.bendT=now()}}
  else if(V.toy==='pads'&&'asdfghjk'.includes(k.toLowerCase())&&k.length===1)V.pad('asdfghjk'.indexOf(k.toLowerCase()));else used=false;if(used)e.preventDefault()});
 // ---- frame ----
 const playing=()=>audioEl?!audioEl.paused:true;
 function frame(t){V.raf=0;if(!V.visible||(o.isVisible&&!o.isVisible()))return;V.raf=requestAnimationFrame(frame);V.frameN++;if(phone&&V.frameN%2)return;// phone: rAF throttled to every other frame (~30 fps)
  const dt=V.lastT?Math.min(100,t-V.lastT):16.7;V.lastT=t;const t0=now();const pl=playing();if(!pl){if(!V.pausedSince)V.pausedSince=t}else V.pausedSince=0;
  if(V.pausedSince&&t-V.pausedSince>2000){if(t-V.lastCalm<500)return;V.lastCalm=t}
  resize();const g=V.g,w=canvas.width,h=canvas.height,F=V.sig.update(t,pl);V.mood.update(F);stepPal(dt);
  V.intens={low:.55,med:1,high:1.35}[V.intensity]||1;V.amp=V.rm?.25:clamp(.45+.8*F.energy,0,1.2)*({low:.7,med:1,high:1.15}[V.intensity]||1);
  if(V.scene==='auto'){const want=autoScene();if(want!==V.active){if(!V.wantSince||V.want!==want){V.want=want;V.wantSince=t}if(t-V.wantSince>30000||V.trackFresh)switchTo(want)}V.trackFresh=false}
  // camera inertia + spring back after 3 s idle
  if(V.inertia&&!V.rm){V.bendX=clamp(V.bendX+V.inertia.vx*dt/1000,-1,1);V.bendY=clamp(V.bendY+V.inertia.vy*dt/1000,-1,1);const dmp=Math.exp(-4*dt/1000);V.inertia.vx*=dmp;V.inertia.vy*=dmp;if(Math.abs(V.inertia.vx)+Math.abs(V.inertia.vy)<.01)V.inertia=null;V.bendT=now()}
  if(!gest&&now()-(V.bendT||0)>3000){V.bendX*=.92;V.bendY*=.92}
  g.setTransform(1,0,0,1,0,0);g.globalAlpha=1;g.globalCompositeOperation='source-over';
  if(V.zoom!==1){g.translate(w/2,h/2);g.scale(V.zoom,V.zoom);g.translate(-w/2,-h/2)}
  SCENES[V.active].frame(V,g,w,h,F,dt);
  if(V.xfade>0&&V.prevSnap){g.setTransform(1,0,0,1,0,0);g.globalAlpha=V.xfade;g.drawImage(V.prevSnap,0,0,w,h);g.globalAlpha=1;V.xfade=Math.max(0,V.xfade-dt/1200);if(!V.xfade)V.prevSnap=null}
  if(V.toy&&TOYS[V.toy].draw)TOYS[V.toy].draw(V,g,w,h,F);
  // scheduled (quantized) taps
  if(V.st.sched&&V.st.sched.length){const n=now();V.st.sched=V.st.sched.filter(s=>{if(n>=s.at){V.burst(s.x,s.y,s.kind);return false}return true})}
  if(V.st.rings){g.globalCompositeOperation='lighter';for(const r of V.st.rings){r.a-=.02*dt/16.7;g.strokeStyle=r.c;g.globalAlpha=Math.max(0,r.a);g.lineWidth=(1+3*r.a)*V.dpr;g.beginPath();g.arc(r.x,r.y,(1-r.a)*Math.min(w,h)*.45+4,0,TAU);g.stroke()}V.st.rings=V.st.rings.filter(r=>r.a>0);g.globalAlpha=1;g.globalCompositeOperation='source-over'}
  // avatar slot (renderer supplied by a registered adapter)
  stepAvatar(g,w,h,F,dt);
  g.setTransform(1,0,0,1,0,0);V.pool.step(g,dt,w,h,V.dpr);
  if(V.st.glow){const q=V.st.glow;const gr=g.createRadialGradient(q.x*w,q.y*h,0,q.x*w,q.y*h,Math.min(w,h)*.2);gr.addColorStop(0,V.pal.glow);gr.addColorStop(1,'transparent');g.globalAlpha=q.a*.5;g.fillStyle=gr;g.fillRect(0,0,w,h);g.globalAlpha=1;q.a-=.03;if(q.a<=0)V.st.glow=null}
  if(F.beat)for(const cb of V.beatCbs)try{cb({bpm:F.bpm,conf:F.conf,phase:F.beatPhase,bar:F.bar,strength:F.strength})}catch(e){}
  if(V.overlay)V.overlay(g,w,h,V.dpr);
  const ms=now()-t0;V.ft.push(ms);if(V.ft.length>240)V.ft.shift();V.fts=(V.fts||[]);V.fts.push(t);while(V.fts.length&&t-V.fts[0]>1000)V.fts.shift();
  V.ema=lerp(V.ema,ms,.05);if(V.ema>budget){V.overT=(V.overT||t);if(t-V.overT>2000&&V.tier<TIERS.length-1){V.tier++;V.overT=0}}else{V.overT=0;if(V.ema<budget*.6){V.underT=V.underT||t;if(t-V.underT>10000&&V.tier>0){V.tier--;V.underT=0}}else V.underT=0}}
 V.start=()=>{if(!V.raf&&V.visible)V.raf=requestAnimationFrame(frame)};V.stop=()=>{if(V.raf)cancelAnimationFrame(V.raf);V.raf=0};
 const api={start(){V.visible=true;V.start()},
  setScene(id){V.scene=id;if(id!=='auto'&&SCENES[id])switchTo(id);else V.trackFresh=true},setAvatar,avatars:listAvatars,selectAvatar(b){V.avSel=!!b&&!!V.avatar},trigger(kind){return V.trigger(kind==='special'?'special':'tap')},setAvatarPos(pos){V.avatarPos=pos||{}},setIntensity(x){V.intensity=x},setStyle(s){V.style=s},
  setTrack(m){V.mood.setTrack(m||{});V.sig.reset(false);V.trackFresh=true;const img=m&&m.artImg;const go=()=>setPalette(paletteFromImage(img,fallbackPal()));if(img&&!img.complete)img.addEventListener('load',go,{once:true});go()},
  onLyric(){},onTransport(k){if(k==='seek'){V.sig.reset(false)}},onBeat(cb){V.beatCbs.push(cb);return()=>{V.beatCbs=V.beatCbs.filter(x=>x!==cb)}},onPointer(cb){V.ptrCbs.push(cb);return()=>{V.ptrCbs=V.ptrCbs.filter(x=>x!==cb)}},
  setToy(t){V.toy=t&&TOYS[t]?t:null;if(V.toy&&TOYS[V.toy].init)TOYS[V.toy].init(V)},setSkin(){},setReducedMotion(b){V.rm=!!b;if(o)o.reducedMotion=V.rm},setVisible(b){V.visible=!!b;b?V.start():V.stop();try{V.avatar&&V.avatar.setVisible&&V.avatar.setVisible(!!b)}catch(e){}},setQuantize(b){V.quantize=!!b},setHaptics(b){V.haptics=!!b},setRiso(b){V.riso=!!b},
  stats(){const a=V.ft.slice().sort((x,y)=>x-y),F=V.sig.F;return {fps:V.fts?V.fts.length:0,p50ms:+(a[a.length>>1]||0).toFixed(2),p95ms:+(a[Math.floor(a.length*.95)]||0).toFixed(2),tier:V.tier,particles:V.pool.p.length,bpm:Math.round(F.idle?96:F.bpm),conf:+F.conf.toFixed(2),idle:F.idle,mood:V.mood.mood,style:V.style==='auto'?V.mood.style:V.style,key:F.key+(F.mode==='minor'?'m':''),keyConf:+F.keyConf.toFixed(2),scene:V.active,sceneSel:V.scene,avatar:V.avatarId,avatarErr:V.avatarErr,avatarMode:V.avatar?V.avatar.mode:null,energy:+F.energy.toFixed(2),bass:+F.bass.toFixed(2),palette:V.pal.src,toy:V.toy,dpr:V.dpr,running:!!V.raf}},
  destroy(){V.stop();setAvatar(null)},probeAvatar,_V:V};
 if(/[?&]vizbench=1/.test(location.search))setInterval(()=>{if(V.raf)console.log('viz.stats',JSON.stringify(api.stats()))},5000);
 return api}
window.MSViz={init,version:'1.2',registerAvatar,avatars:listAvatars,SCENES,TOYS,Signal,paletteFromImage};
})();
