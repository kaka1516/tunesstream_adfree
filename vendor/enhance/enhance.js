/* enhance-20261111 — Music Stream "Enhance": client-side audio + video enhancement. Runs only in the listener's browser.
   Audio: native Web Audio nodes (10-band EQ, bass shelf, clarity/presence + air shelves, mid/side stereo width, headroom + limiter),
          inserted AFTER the player's existing volume-levelling stage (normInit/normApply: compressor + makeup gain) — no duplicate leveller.
          If the AudioContext cannot be created/resumed, the player's <audio> element plays untouched (normInit never ran).
   Video: AMD FidelityFX Super Resolution 1 (EASU upscale + RCAS sharpen) re-implemented as WebGPU (WGSL) and WebGL (GLSL ES 1.0) shaders,
          drawn to a canvas laid exactly over the muted <video> (inherits Fit/Fill, fullscreen; never covers controls; pointer-events:none).
          Path order: WebGPU -> WebGL -> plain video. Auto-steps down (Upscale -> Sharpen -> Off) when frames cost too much or frames drop.
   FSR 1 algorithm: Copyright (c) 2021 Advanced Micro Devices, Inc. — MIT License (GPUOpen-Effects/FidelityFX-FSR). See THIRD_PARTY_NOTICES.md. */
(function(){'use strict';if(window.MSEnh)return;
const LS=window.localStorage,KEY='enh',$=id=>document.getElementById(id);
const IOS=/iphone|ipad|ipod/i.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
const PHONE=matchMedia('(max-width:600px),(max-height:500px),(pointer:coarse)').matches;
const BANDS=[31,62,125,250,500,1000,2000,4000,8000,16000];
const PRESETS={off:{n:'Off'},
 balanced:{n:'Balanced',eq:[1,1,.5,0,0,0,.5,1,1,.5],bass:1,clar:1,width:10},
 bass:{n:'Bass boost',eq:[4,3.5,2,.5,-.5,0,0,.5,.5,0],bass:4,clar:.5,width:10},
 vocal:{n:'Vocal clarity',eq:[-1.5,-1,-.5,0,1,2,3,2,1,0],bass:0,clar:2.5,width:0},
 cinema:{n:'Telugu film',eq:[2.5,2,1,0,-.5,.5,1.5,2,2,1.5],bass:2.5,clar:1.5,width:25},
 night:{n:'Night',eq:[-2,-1.5,-.5,0,.5,1,1,0,-1,-2],bass:-1,clar:1,width:0,level:true}};
const DEF={on:false,preset:'balanced',eq:PRESETS.balanced.eq.slice(),bass:1,clar:1,width:10,video:'off'};
function load(){let s={};try{s=JSON.parse(LS.getItem(KEY)||'{}')||{}}catch(e){}const o=Object.assign({},DEF,s);
 if(!Array.isArray(o.eq)||o.eq.length!==10)o.eq=DEF.eq.slice();o.eq=o.eq.map(x=>clamp(+x||0,-12,12));o.bass=clamp(+o.bass||0,-6,9);o.clar=clamp(+o.clar||0,-6,6);o.width=clamp(+o.width||0,0,60);
 if(!['off','sharpen','upscale'].includes(o.video))o.video='off';return o}
function clamp(x,a,b){return Math.max(a,Math.min(b,x))}
let st=load();
function save(){try{LS.setItem(KEY,JSON.stringify(st))}catch(e){}}
const say=m=>{try{if(typeof toast==='function')toast(m)}catch(e){}};
const AUDel=()=>{try{return (typeof AUD!=='undefined'&&AUD)||$('aud')}catch(e){return $('aud')}};

/* ====================================== AUDIO ====================================== */
const A={g:null,ok:false,err:''};
function dbg(x){return Math.pow(10,x/20)}
function attach(G){ // G={AC,src,outs:[nDry,nWet]} from player.html normInit()
 if(!G||!G.AC||A.g&&A.g.AC===G.AC)return;try{const AC=G.AC;
  const inp=AC.createGain(),dry=AC.createGain(),wet=AC.createGain();dry.gain.value=1;wet.gain.value=0;
  const up=AC.createGain();up.channelCount=2;up.channelCountMode='explicit';up.channelInterpretation='speakers'; // mono -> stereo before M/S
  const eq=BANDS.map((f,i)=>{const b=AC.createBiquadFilter();b.type=i===0?'lowshelf':i===9?'highshelf':'peaking';b.frequency.value=f;b.Q.value=1.1;b.gain.value=0;return b});
  const bass=AC.createBiquadFilter();bass.type='lowshelf';bass.frequency.value=110;
  const pres=AC.createBiquadFilter();pres.type='peaking';pres.frequency.value=3200;pres.Q.value=.9;
  const air=AC.createBiquadFilter();air.type='highshelf';air.frequency.value=9500;
  const sp=AC.createChannelSplitter(2),mg=AC.createChannelMerger(2),gLL=AC.createGain(),gLR=AC.createGain(),gRL=AC.createGain(),gRR=AC.createGain();
  const pre=AC.createGain(),lim=AC.createDynamicsCompressor();lim.threshold.value=-3;lim.knee.value=0;lim.ratio.value=20;lim.attack.value=.002;lim.release.value=.1;
  const an=AC.createAnalyser();an.fftSize=2048;
  // wire: inp -> up -> eq... -> bass -> pres -> air -> splitter/MS -> merger -> pre -> lim -> wet -> dest
  let n=up;eq.forEach(b=>{n.connect(b);n=b});n.connect(bass);bass.connect(pres);pres.connect(air);air.connect(sp);
  sp.connect(gLL,0);sp.connect(gLR,0);sp.connect(gRL,1);sp.connect(gRR,1);gLL.connect(mg,0,0);gRL.connect(mg,0,0);gLR.connect(mg,0,1);gRR.connect(mg,0,1);
  mg.connect(pre);pre.connect(lim);lim.connect(wet);
  inp.connect(dry);dry.connect(AC.destination);wet.connect(AC.destination);inp.connect(an);/* analyser = what reaches the speakers (pre-mix tap below) */
  const outAn=AC.createAnalyser();outAn.fftSize=2048;dry.connect(outAn);wet.connect(outAn);
  (G.outs||[]).forEach(o=>{try{o.disconnect()}catch(e){}o.connect(inp)});
  A.g={AC,inp,dry,wet,up,eq,bass,pres,air,gLL,gLR,gRL,gRR,pre,lim,an:outAn,inAn:an,linked:false};A.ok=true;
  AC.addEventListener&&AC.addEventListener('statechange',()=>{A.state=AC.state;ui()});
  applyAudio(true)}catch(e){A.err=String(e&&e.message||e);A.ok=false;console.warn('enhance attach',e)}}
function applyAudio(now){const g=A.g;if(!g)return;const AC=g.AC,t=AC.currentTime,tc=now?.001:.03,on=!!st.on;
 if(on&&!g.linked){g.inp.connect(g.up);g.linked=true}
 st.eq.forEach((v,i)=>g.eq[i].gain.setTargetAtTime(v,t,tc));g.bass.gain.setTargetAtTime(st.bass,t,tc);
 g.pres.gain.setTargetAtTime(st.clar,t,tc);g.air.gain.setTargetAtTime(st.clar*.6,t,tc);
 const k=1+st.width/100,a=(1+k)/2,b=(1-k)/2;g.gLL.gain.setTargetAtTime(a,t,tc);g.gRR.gain.setTargetAtTime(a,t,tc);g.gLR.gain.setTargetAtTime(b,t,tc);g.gRL.gain.setTargetAtTime(b,t,tc);
 // headroom: half of the biggest boost so the limiter only catches peaks instead of squashing everything
 const peak=Math.max(0,...st.eq,st.bass+Math.max(0,st.eq[0],st.eq[1]),st.clar);g.pre.gain.setTargetAtTime(dbg(-peak*.55),t,tc);
 g.wet.gain.setTargetAtTime(on?1:0,t,tc);g.dry.gain.setTargetAtTime(on?0:1,t,tc);
 if(!on&&g.linked){clearTimeout(A.unl);A.unl=setTimeout(()=>{if(!st.on&&g.linked){try{g.inp.disconnect(g.up)}catch(e){}g.linked=false}},250)}/* off = no DSP cost */
 if(AC.state!=='running')AC.resume().catch(()=>{})}
/* Create the graph only on a real user gesture (autoplay policy) and only when Enhance is on; otherwise never touch the element. */
function ensureCtx(){if(A.g)return true;if(!st.on)return false;try{if(typeof normInit==='function'){normInit();if(typeof normApply==='function')normApply()}}catch(e){A.err=String(e)}
 if(!A.g&&window.__msEnhG)attach(window.__msEnhG);return !!A.g}
['pointerdown','keydown','touchend'].forEach(ev=>document.addEventListener(ev,()=>{if(st.on&&!A.g)ensureCtx();const g=A.g;if(g&&g.AC.state!=='running'&&g.AC.state!=='closed')g.AC.resume().catch(()=>{})},{capture:true,passive:true}));
/* Watchdog: the element keeps playing even if the context is suspended (Android power save / iOS interruption), so try to resume. */
function wd(){const g=A.g,a=AUDel();if(!g||!a)return;if(!a.paused&&g.AC.state!=='running'&&g.AC.state!=='closed'){g.AC.resume().then(()=>{A.stall=0}).catch(()=>{});A.stall=(A.stall||0)+1;if(A.stall===3)say('Tap anywhere to bring the sound back')}else A.stall=0}
setInterval(wd,700);document.addEventListener('visibilitychange',wd);
function hookAud(){const a=AUDel();if(!a||a.__enh)return;a.__enh=1;a.addEventListener('play',wd);a.addEventListener('playing',wd)}
function levels(){const g=A.g;if(!g)return null;const b=new Float32Array(g.an.fftSize);g.an.getFloatTimeDomainData(b);let pk=0,s=0;for(const v of b){const x=Math.abs(v);if(x>pk)pk=x;s+=v*v}
 return {state:g.AC.state,peak:+pk.toFixed(4),rms:+Math.sqrt(s/b.length).toFixed(4),on:st.on,linked:g.linked,level:typeof normOn!=='undefined'?!!normOn:null}}

/* ====================================== VIDEO ====================================== */
const WGSL_COMMON=`
fn lum(c:vec3<f32>)->f32{return c.b*0.5+(c.r*0.5+c.g);}
`;
const WGSL_VS=`struct O{@builtin(position) p:vec4<f32>};@vertex fn vs(@builtin(vertex_index) i:u32)->O{var P=array<vec2<f32>,3>(vec2(-1.,-1.),vec2(3.,-1.),vec2(-1.,3.));var o:O;o.p=vec4(P[i],0.,1.);return o;}`;
function wgslEASU(){return WGSL_VS+WGSL_COMMON+`
@group(0) @binding(0) var T:texture_external;
struct U{inS:vec2<f32>,outS:vec2<f32>,sh:vec4<f32>};@group(0) @binding(1) var<uniform> u:U;
fn ld(p:vec2<f32>)->vec3<f32>{let d=vec2<i32>(textureDimensions(T));let q=clamp(vec2<i32>(p),vec2<i32>(0),d-vec2<i32>(1));return textureLoad(T,q).rgb;}
fn setF(dir:ptr<function,vec2<f32>>,len:ptr<function,f32>,w:f32,lA:f32,lB:f32,lC:f32,lD:f32,lE:f32){
 let dc=lD-lC;let cb=lC-lB;var lx=max(abs(dc),abs(cb));lx=1.0/max(lx,1e-5);let dx=lD-lB;(*dir).x+=dx*w;lx=clamp(abs(dx)*lx,0.,1.);lx*=lx;(*len)+=lx*w;
 let ec=lE-lC;let ca=lC-lA;var ly=max(abs(ec),abs(ca));ly=1.0/max(ly,1e-5);let dy=lE-lA;(*dir).y+=dy*w;ly=clamp(abs(dy)*ly,0.,1.);ly*=ly;(*len)+=ly*w;}
fn tap(aC:ptr<function,vec3<f32>>,aW:ptr<function,f32>,off:vec2<f32>,dir:vec2<f32>,len:vec2<f32>,lob:f32,clp:f32,c:vec3<f32>){
 var v=vec2(off.x*dir.x+off.y*dir.y,off.x*(-dir.y)+off.y*dir.x);v*=len;let d2=min(v.x*v.x+v.y*v.y,clp);
 var wB=(2./5.)*d2-1.;var wA=lob*d2-1.;wB*=wB;wA*=wA;wB=(25./16.)*wB-(25./16.-1.);let w=wB*wA;(*aC)+=c*w;(*aW)+=w;}
@fragment fn fs(@builtin(position) fc:vec4<f32>)->@location(0) vec4<f32>{
 var pp=fc.xy*(u.inS/u.outS)-vec2(0.5);let fp=floor(pp);pp-=fp;
 let b=ld(fp+vec2(0.,-1.));let c=ld(fp+vec2(1.,-1.));let e=ld(fp+vec2(-1.,0.));let f=ld(fp);let g=ld(fp+vec2(1.,0.));let h=ld(fp+vec2(2.,0.));
 let i=ld(fp+vec2(-1.,1.));let j=ld(fp+vec2(0.,1.));let k=ld(fp+vec2(1.,1.));let l=ld(fp+vec2(2.,1.));let n=ld(fp+vec2(0.,2.));let o=ld(fp+vec2(1.,2.));
 let bL=lum(b);let cL=lum(c);let eL=lum(e);let fL=lum(f);let gL=lum(g);let hL=lum(h);let iL=lum(i);let jL=lum(j);let kL=lum(k);let lL=lum(l);let nL=lum(n);let oL=lum(o);
 var dir=vec2(0.);var len=0.;
 setF(&dir,&len,(1.-pp.x)*(1.-pp.y),bL,eL,fL,gL,jL);setF(&dir,&len,pp.x*(1.-pp.y),cL,fL,gL,hL,kL);
 setF(&dir,&len,(1.-pp.x)*pp.y,fL,iL,jL,kL,nL);setF(&dir,&len,pp.x*pp.y,gL,jL,kL,lL,oL);
 let d2=dir*dir;var dr=d2.x+d2.y;let zro=dr<1.0/32768.0;dr=inverseSqrt(max(dr,1e-12));if(zro){dr=1.;dir.x=1.;}dir*=dr;
 len=len*0.5;len*=len;let stch=(dir.x*dir.x+dir.y*dir.y)/max(abs(dir.x),abs(dir.y));let len2=vec2(1.+(stch-1.)*len,1.-0.5*len);
 let lob=0.5+((1./4.-0.04)-0.5)*len;let clp=1./lob;
 let mn=min(min(f,g),min(j,k));let mx=max(max(f,g),max(j,k));var aC=vec3(0.);var aW=0.;
 tap(&aC,&aW,vec2(0.,-1.)-pp,dir,len2,lob,clp,b);tap(&aC,&aW,vec2(1.,-1.)-pp,dir,len2,lob,clp,c);tap(&aC,&aW,vec2(-1.,1.)-pp,dir,len2,lob,clp,i);
 tap(&aC,&aW,vec2(0.,1.)-pp,dir,len2,lob,clp,j);tap(&aC,&aW,vec2(0.,0.)-pp,dir,len2,lob,clp,f);tap(&aC,&aW,vec2(-1.,0.)-pp,dir,len2,lob,clp,e);
 tap(&aC,&aW,vec2(1.,1.)-pp,dir,len2,lob,clp,k);tap(&aC,&aW,vec2(2.,1.)-pp,dir,len2,lob,clp,l);tap(&aC,&aW,vec2(2.,0.)-pp,dir,len2,lob,clp,h);
 tap(&aC,&aW,vec2(1.,0.)-pp,dir,len2,lob,clp,g);tap(&aC,&aW,vec2(1.,2.)-pp,dir,len2,lob,clp,o);tap(&aC,&aW,vec2(0.,2.)-pp,dir,len2,lob,clp,n);
 return vec4(min(mx,max(mn,aC/aW)),1.);}`}
function wgslRCAS(ext){return WGSL_VS+WGSL_COMMON+(ext?`@group(0) @binding(0) var T:texture_external;`:`@group(0) @binding(0) var T:texture_2d<f32>;`)+`
struct U{inS:vec2<f32>,outS:vec2<f32>,sh:vec4<f32>};@group(0) @binding(1) var<uniform> u:U;
fn ld(p:vec2<f32>)->vec3<f32>{let d=vec2<i32>(textureDimensions(T));let q=clamp(vec2<i32>(p),vec2<i32>(0),d-vec2<i32>(1));return textureLoad(T,q${ext?'':',0'}).rgb;}
@fragment fn fs(@builtin(position) fc:vec4<f32>)->@location(0) vec4<f32>{let ip=floor(fc.xy);
 let b=ld(ip+vec2(0.,-1.));let d=ld(ip+vec2(-1.,0.));let e=ld(ip);let f=ld(ip+vec2(1.,0.));let h=ld(ip+vec2(0.,1.));
 let bL=lum(b);let dL=lum(d);let eL=lum(e);let fL=lum(f);let hL=lum(h);
 var nz=0.25*(bL+dL+fL+hL)-eL;let rng=max(max(max(bL,dL),max(eL,fL)),hL)-min(min(min(bL,dL),min(eL,fL)),hL);nz=clamp(abs(nz)/max(rng,1e-5),0.,1.);nz=-0.5*nz+1.;
 let mn4=min(min(b,d),min(f,h));let mx4=max(max(b,d),max(f,h));
 let hitMin=min(mn4,e)/max(4.*mx4,vec3(1e-5));let hitMax=(1.-max(mx4,e))/min(4.*mn4-4.,vec3(-1e-5));
 let lr=max(-hitMin,hitMax);var lobe=max(-(0.25-1./16.),min(max(lr.r,max(lr.g,lr.b)),0.))*u.sh.x;lobe*=nz;
 let o=(lobe*(b+d+f+h)+e)/(4.*lobe+1.);return vec4(clamp(o,vec3(0.),vec3(1.)),1.);}`}
const GL_VS='attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
const GL_HEAD='#ifdef GL_FRAGMENT_PRECISION_HIGH\nprecision highp float;\n#else\nprecision mediump float;\n#endif\nuniform sampler2D T;uniform vec2 inS;uniform vec2 outS;uniform float sh;\nfloat lum(vec3 c){return c.b*0.5+(c.r*0.5+c.g);}\n'+
 /* all textures are stored bottom-up (video uploaded with UNPACK_FLIP_Y); ld() takes FSR's top-down pixel coords */
 'vec3 ld(vec2 p){p=clamp(p,vec2(0.),inS-1.);return texture2D(T,vec2(p.x+0.5,inS.y-0.5-p.y)/inS).rgb;}\nvec2 td(){return vec2(gl_FragCoord.x,outS.y-gl_FragCoord.y);}\n';
const GL_EASU=GL_HEAD+`
void setF(inout vec2 dir,inout float len,float w,float lA,float lB,float lC,float lD,float lE){
 float dc=lD-lC,cb=lC-lB,lx=1./max(max(abs(dc),abs(cb)),1e-5),dx=lD-lB;dir.x+=dx*w;lx=clamp(abs(dx)*lx,0.,1.);lx*=lx;len+=lx*w;
 float ec=lE-lC,ca=lC-lA,ly=1./max(max(abs(ec),abs(ca)),1e-5),dy=lE-lA;dir.y+=dy*w;ly=clamp(abs(dy)*ly,0.,1.);ly*=ly;len+=ly*w;}
void tap(inout vec3 aC,inout float aW,vec2 off,vec2 dir,vec2 len,float lob,float clp,vec3 c){
 vec2 v=vec2(off.x*dir.x+off.y*dir.y,off.x*(-dir.y)+off.y*dir.x)*len;float d2=min(dot(v,v),clp);
 float wB=(2./5.)*d2-1.,wA=lob*d2-1.;wB*=wB;wA*=wA;wB=(25./16.)*wB-(25./16.-1.);float w=wB*wA;aC+=c*w;aW+=w;}
void main(){vec2 pp=td()*(inS/outS)-0.5;vec2 fp=floor(pp);pp-=fp;
 vec3 b=ld(fp+vec2(0.,-1.)),c=ld(fp+vec2(1.,-1.)),e=ld(fp+vec2(-1.,0.)),f=ld(fp),g=ld(fp+vec2(1.,0.)),h=ld(fp+vec2(2.,0.)),
      i=ld(fp+vec2(-1.,1.)),j=ld(fp+vec2(0.,1.)),k=ld(fp+vec2(1.,1.)),l=ld(fp+vec2(2.,1.)),n=ld(fp+vec2(0.,2.)),o=ld(fp+vec2(1.,2.));
 float bL=lum(b),cL=lum(c),eL=lum(e),fL=lum(f),gL=lum(g),hL=lum(h),iL=lum(i),jL=lum(j),kL=lum(k),lL=lum(l),nL=lum(n),oL=lum(o);
 vec2 dir=vec2(0.);float len=0.;vec2 q=pp;
 setF(dir,len,(1.-q.x)*(1.-q.y),bL,eL,fL,gL,jL);setF(dir,len,q.x*(1.-q.y),cL,fL,gL,hL,kL);setF(dir,len,(1.-q.x)*q.y,fL,iL,jL,kL,nL);setF(dir,len,q.x*q.y,gL,jL,kL,lL,oL);
 vec2 d2=dir*dir;float dr=d2.x+d2.y;bool zro=dr<1./32768.;dr=inversesqrt(max(dr,1e-12));if(zro){dr=1.;dir.x=1.;}dir*=dr;
 len=len*0.5;len*=len;float stch=dot(dir,dir)/max(abs(dir.x),abs(dir.y));vec2 len2=vec2(1.+(stch-1.)*len,1.-0.5*len);float lob=0.5+((1./4.-0.04)-0.5)*len,clp=1./lob;
 vec3 mn=min(min(f,g),min(j,k)),mx=max(max(f,g),max(j,k));vec3 aC=vec3(0.);float aW=0.;
 tap(aC,aW,vec2(0.,-1.)-q,dir,len2,lob,clp,b);tap(aC,aW,vec2(1.,-1.)-q,dir,len2,lob,clp,c);tap(aC,aW,vec2(-1.,1.)-q,dir,len2,lob,clp,i);
 tap(aC,aW,vec2(0.,1.)-q,dir,len2,lob,clp,j);tap(aC,aW,vec2(0.,0.)-q,dir,len2,lob,clp,f);tap(aC,aW,vec2(-1.,0.)-q,dir,len2,lob,clp,e);
 tap(aC,aW,vec2(1.,1.)-q,dir,len2,lob,clp,k);tap(aC,aW,vec2(2.,1.)-q,dir,len2,lob,clp,l);tap(aC,aW,vec2(2.,0.)-q,dir,len2,lob,clp,h);
 tap(aC,aW,vec2(1.,0.)-q,dir,len2,lob,clp,g);tap(aC,aW,vec2(1.,2.)-q,dir,len2,lob,clp,o);tap(aC,aW,vec2(0.,2.)-q,dir,len2,lob,clp,n);
 gl_FragColor=vec4(min(mx,max(mn,aC/aW)),1.);}`;
const GL_RCAS=GL_HEAD+`
void main(){vec2 ip=floor(td());vec3 b=ld(ip+vec2(0.,-1.)),d=ld(ip+vec2(-1.,0.)),e=ld(ip),f=ld(ip+vec2(1.,0.)),h=ld(ip+vec2(0.,1.));
 float bL=lum(b),dL=lum(d),eL=lum(e),fL=lum(f),hL=lum(h);float nz=0.25*(bL+dL+fL+hL)-eL;
 float rng=max(max(max(bL,dL),max(eL,fL)),hL)-min(min(min(bL,dL),min(eL,fL)),hL);nz=clamp(abs(nz)/max(rng,1e-5),0.,1.);nz=-0.5*nz+1.;
 vec3 mn4=min(min(b,d),min(f,h)),mx4=max(max(b,d),max(f,h));vec3 hitMin=min(mn4,e)/max(4.*mx4,vec3(1e-5));vec3 hitMax=(1.-max(mx4,e))/min(4.*mn4-4.,vec3(-1e-5));
 vec3 lr=max(-hitMin,hitMax);float lobe=max(-(0.25-1./16.),min(max(lr.r,max(lr.g,lr.b)),0.))*sh;lobe*=nz;
 gl_FragColor=vec4(clamp((lobe*(b+d+f+h)+e)/(4.*lobe+1.),0.,1.),1.);}`;

const VX={path:null,want:null,cv:null,r:null,vid:null,cb:0,frames:0,cost:[],cpu:[],t0:0,fps:0,fcount:0,fts:0,drop0:null,drop:{},off:'',busy:false,src:[0,0],out:[0,0],note:'',lastDraw:0,noGPU:false,noGL:false};
const SHARP={sharpen:Math.pow(2,-0.25),upscale:Math.pow(2,-0.35)};
function curVid(){return window.VID||$('vid')}
function stageOn(){const s=$('stage'),v=curVid();return !!(s&&v&&s.classList.contains('video')&&v.videoWidth>0&&getComputedStyle(v).display!=='none'&&s.offsetWidth>0)}
function newCanvas(){if(VX.cv)VX.cv.remove();const c=document.createElement('canvas');c.id='enhcv';c.setAttribute('aria-hidden','true');
 c.style.cssText='position:absolute;pointer-events:none;z-index:1;display:none;background:transparent';VX.cv=c;return c}
async function initGPU(){const ad=await navigator.gpu.requestAdapter({powerPreference:PHONE?'low-power':'high-performance'});if(!ad)throw new Error('no adapter');
 const dev=await ad.requestDevice();const c=newCanvas(),ctx=c.getContext('webgpu');if(!ctx)throw new Error('no webgpu ctx');const fmt=navigator.gpu.getPreferredCanvasFormat();ctx.configure({device:dev,format:fmt,alphaMode:'opaque'});
 dev.lost.then(i=>{if(VX.r&&VX.r.dev===dev){VX.noGPU=true;fallback('WebGPU device lost: '+(i&&i.message||''))}});
 let err=null;dev.onuncapturederror=e=>{err=e.error&&e.error.message||'gpu error';if(VX.r&&VX.r.dev===dev){VX.noGPU=true;fallback('WebGPU error: '+err)}};
 const mk=(code,f)=>{const m=dev.createShaderModule({code});return dev.createRenderPipeline({layout:'auto',vertex:{module:m,entryPoint:'vs'},fragment:{module:m,entryPoint:'fs',targets:[{format:f}]},primitive:{topology:'triangle-list'}})};
 const easu=mk(wgslEASU(),'rgba8unorm'),rcasX=mk(wgslRCAS(true),fmt),rcasT=mk(wgslRCAS(false),fmt);
 const ub=dev.createBuffer({size:32,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST}),ub2=dev.createBuffer({size:32,usage:GPUBufferUsage.UNIFORM|GPUBufferUsage.COPY_DST});
 let mid=null,midS='';
 const R={kind:'webgpu',dev,ctx,draw(v,mode,ow,oh,measure){const vw=v.videoWidth,vh=v.videoHeight;
   const ext=dev.importExternalTexture({source:v});const enc=dev.createCommandEncoder();
   if(mode==='upscale'){if(midS!==ow+'x'+oh){if(mid)mid.destroy();mid=dev.createTexture({size:[ow,oh],format:'rgba8unorm',usage:GPUTextureUsage.RENDER_ATTACHMENT|GPUTextureUsage.TEXTURE_BINDING});midS=ow+'x'+oh}
    dev.queue.writeBuffer(ub,0,new Float32Array([vw,vh,ow,oh,1,0,0,0]));dev.queue.writeBuffer(ub2,0,new Float32Array([ow,oh,ow,oh,SHARP.upscale,0,0,0]));
    const p1=enc.beginRenderPass({colorAttachments:[{view:mid.createView(),loadOp:'clear',storeOp:'store',clearValue:[0,0,0,1]}]});p1.setPipeline(easu);
    p1.setBindGroup(0,dev.createBindGroup({layout:easu.getBindGroupLayout(0),entries:[{binding:0,resource:ext},{binding:1,resource:{buffer:ub}}]}));p1.draw(3);p1.end();
    const p2=enc.beginRenderPass({colorAttachments:[{view:ctx.getCurrentTexture().createView(),loadOp:'clear',storeOp:'store',clearValue:[0,0,0,1]}]});p2.setPipeline(rcasT);
    p2.setBindGroup(0,dev.createBindGroup({layout:rcasT.getBindGroupLayout(0),entries:[{binding:0,resource:mid.createView()},{binding:1,resource:{buffer:ub2}}]}));p2.draw(3);p2.end()}
   else{dev.queue.writeBuffer(ub2,0,new Float32Array([vw,vh,vw,vh,SHARP.sharpen,0,0,0]));
    const p2=enc.beginRenderPass({colorAttachments:[{view:ctx.getCurrentTexture().createView(),loadOp:'clear',storeOp:'store',clearValue:[0,0,0,1]}]});p2.setPipeline(rcasX);
    p2.setBindGroup(0,dev.createBindGroup({layout:rcasX.getBindGroupLayout(0),entries:[{binding:0,resource:ext},{binding:1,resource:{buffer:ub2}}]}));p2.draw(3);p2.end()}
   dev.queue.submit([enc.finish()]);if(measure){const t=performance.now();return dev.queue.onSubmittedWorkDone().then(()=>performance.now()-t)}return null},
  destroy(){try{mid&&mid.destroy();dev.destroy()}catch(e){}}};
 return R}
function initGL(){const c=newCanvas();const o={alpha:false,antialias:false,depth:false,stencil:false,premultipliedAlpha:false,preserveDrawingBuffer:false,powerPreference:PHONE?'low-power':'high-performance'};
 const gl=c.getContext('webgl2',o)||c.getContext('webgl',o);if(!gl)throw new Error('no webgl');
 c.addEventListener('webglcontextlost',e=>{e.preventDefault();if(VX.r&&VX.r.gl===gl){VX.noGL=true;fallback('WebGL context lost')}});
 const sh=(t,s)=>{const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(x));return x};
 const prog=fs=>{const p=gl.createProgram();gl.attachShader(p,sh(gl.VERTEX_SHADER,GL_VS));gl.attachShader(p,sh(gl.FRAGMENT_SHADER,fs));gl.bindAttribLocation(p,0,'p');gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));
  return {p,T:gl.getUniformLocation(p,'T'),inS:gl.getUniformLocation(p,'inS'),outS:gl.getUniformLocation(p,'outS'),sh:gl.getUniformLocation(p,'sh')}};
 const E=prog(GL_EASU),Rc=prog(GL_RCAS);const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,3,-1,-1,3]),gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,2,gl.FLOAT,false,0,0);
 const tex=()=>{const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);[gl.TEXTURE_MIN_FILTER,gl.TEXTURE_MAG_FILTER].forEach(k=>gl.texParameteri(gl.TEXTURE_2D,k,gl.NEAREST));gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return t};
 const vt=tex(),mt=tex(),fb=gl.createFramebuffer();let mS='';
 const R={kind:(typeof WebGL2RenderingContext!=='undefined'&&gl instanceof WebGL2RenderingContext)?'webgl2':'webgl',gl,draw(v,mode,ow,oh,measure){const vw=v.videoWidth,vh=v.videoHeight;
   gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,vt);gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL,true);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,v);
   const t0=performance.now();
   if(mode==='upscale'){gl.bindTexture(gl.TEXTURE_2D,mt);if(mS!==ow+'x'+oh){gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,ow,oh,0,gl.RGBA,gl.UNSIGNED_BYTE,null);mS=ow+'x'+oh}
    gl.bindFramebuffer(gl.FRAMEBUFFER,fb);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,mt,0);gl.viewport(0,0,ow,oh);
    gl.useProgram(E.p);gl.bindTexture(gl.TEXTURE_2D,vt);gl.uniform1i(E.T,0);gl.uniform2f(E.inS,vw,vh);gl.uniform2f(E.outS,ow,oh);gl.drawArrays(gl.TRIANGLES,0,3);
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,ow,oh);gl.useProgram(Rc.p);gl.bindTexture(gl.TEXTURE_2D,mt);gl.uniform1i(Rc.T,0);gl.uniform2f(Rc.inS,ow,oh);gl.uniform2f(Rc.outS,ow,oh);gl.uniform1f(Rc.sh,SHARP.upscale);gl.drawArrays(gl.TRIANGLES,0,3)}
   else{gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,vw,vh);gl.useProgram(Rc.p);gl.uniform1i(Rc.T,0);gl.uniform2f(Rc.inS,vw,vh);gl.uniform2f(Rc.outS,vw,vh);gl.uniform1f(Rc.sh,SHARP.sharpen);gl.drawArrays(gl.TRIANGLES,0,3)}
   if(measure){const px=new Uint8Array(4);gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,px);return performance.now()-t0}/* readPixels = sync point -> upper bound of GPU time for this frame */
   return null},destroy(){try{const x=gl.getExtension('WEBGL_lose_context');x&&x.loseContext()}catch(e){}}};
 return R}
let initP=null;
async function ensureR(){if(VX.r)return VX.r;if(initP)return initP;initP=(async()=>{let r=null,why=[];
  if(!VX.noGPU&&navigator.gpu&&!/[?&]enh=gl\b/.test(location.search)){try{r=await initGPU()}catch(e){why.push('WebGPU: '+(e&&e.message||e));VX.noGPU=true}}
  if(!r&&!VX.noGL){try{r=initGL()}catch(e){why.push('WebGL: '+(e&&e.message||e));VX.noGL=true}}
  VX.r=r;VX.path=r?r.kind:'none';VX.note=why.join(' | ');if(!r){VX.cv&&VX.cv.remove();VX.cv=null}initP=null;return r})();return initP}
function fallback(why){const r=VX.r;VX.r=null;VX.note=(VX.note?VX.note+' | ':'')+why;try{r&&r.destroy()}catch(e){}if(VX.cv){VX.cv.remove();VX.cv=null}VX.vid=null;
 console.warn('enhance video fallback:',why);if(st.video!=='off')setTimeout(sync,50)}
function outSize(v){const vw=v.videoWidth,vh=v.videoHeight,r=v.getBoundingClientRect(),fit=getComputedStyle(v).objectFit;
 const s=fit==='cover'?Math.max(r.width/vw,r.height/vh):Math.min(r.width/vw,r.height/vh);const dpr=Math.min(PHONE?2:2,devicePixelRatio||1);
 let ow=vw*s*dpr,oh=vh*s*dpr;const cap=PHONE?1920:2560,k=Math.min(1,cap/Math.max(ow,oh));ow=Math.round(ow*k);oh=Math.round(oh*k);return [ow,oh]}
function place(v){const c=VX.cv,s=$('stage');if(!c||!s)return;if(c.previousElementSibling!==v)v.after(c);
 const sr=s.getBoundingClientRect(),vr=v.getBoundingClientRect(),cs=getComputedStyle(v);
 c.style.left=(vr.left-sr.left-s.clientLeft+s.scrollLeft)+'px';c.style.top=(vr.top-sr.top-s.clientTop+s.scrollTop)+'px';c.style.width=vr.width+'px';c.style.height=vr.height+'px';
 c.style.objectFit=cs.objectFit;c.style.objectPosition=cs.objectPosition;c.style.borderRadius=cs.borderRadius;c.style.display='block'}
function effMode(v,ow,oh){if(st.video==='upscale'&&ow>v.videoWidth*1.1)return 'upscale';return 'sharpen'}
function frame(force){const v=VX.vid,r=VX.r,c=VX.cv;if(!v||!r||!c||st.video==='off')return;if(v.readyState<2)return;
 const [ow0,oh0]=outSize(v),mode=effMode(v,ow0,oh0),ow=mode==='upscale'?ow0:v.videoWidth,oh=mode==='upscale'?oh0:v.videoHeight;
 if(c.width!==ow||c.height!==oh){c.width=ow;c.height=oh;if(r.kind==='webgpu'){/* canvas resize re-sizes swapchain automatically */}}
 VX.src=[v.videoWidth,v.videoHeight];VX.out=[ow,oh];VX.mode=mode;place(v);
 const measure=(VX.frames%20)===0&&VX.frames-(VX.warm||0)>30,/* skip shader-compile / first-upload frames */c0=performance.now();let res=null;
 try{res=r.draw(v,mode,ow,oh,measure)}catch(e){fallback((r.kind||'gpu')+' draw failed: '+(e&&e.message||e));return}
 VX.cpu.push(performance.now()-c0);if(VX.cpu.length>30)VX.cpu.shift();
 const push=ms=>{VX.cost.push(ms+(+window.__msEnhTestCost||0));/* test hook: simulate a slow GPU */if(VX.cost.length>8)VX.cost.shift();budget()};
 if(res&&res.then)res.then(push).catch(()=>{});else if(typeof res==='number')push(res);
 VX.frames++;VX.lastDraw=performance.now();const t=performance.now();if(!VX.fts)VX.fts=t;VX.fcount++;if(t-VX.fts>=1000){VX.fps=Math.round(VX.fcount*1000/(t-VX.fts));VX.fcount=0;VX.fts=t}}
function vfps(v){return Math.max(24,Math.min(60,VX.vfps||30))}
function budget(){if(VX.cost.length<6||window.__msEnhNoAuto)return;const so=VX.cost.slice().sort((a,b)=>a-b),avg=so[so.length>>1],/* median: one slow frame is not a reason to switch off */b=Math.max(8,1000/vfps()*.5);/* half a frame interval for us, rest for the page */
 if(avg>b)stepDown('each frame took '+avg.toFixed(1)+' ms (budget '+b.toFixed(0)+' ms)')}
function stepDown(why){if(VX.r&&VX.r.kind==='webgpu'&&!VX.noGL&&!VX.triedGL){VX.triedGL=true;VX.noGPU=true;VX.cost=[];VX.autoOff={from:'webgpu',to:'webgl',why,at:Date.now()};fallback('WebGPU too slow here ('+why+'), trying WebGL');return}/* same mode on the other path first */
 const from=st.video;VX.off=why;VX.cost=[];VX.warm=VX.frames;if(VX.mode==='upscale'&&from==='upscale'){st.video='sharpen';say('Video: Upscale was too heavy here, using Sharpen')}else{st.video='off';say('Video enhance turned off: this device is too slow for it')}
 VX.autoOff={from,to:st.video,why,at:Date.now()};save();ui();sync()}
function dropCheck(){const v=VX.vid;if(!v||!v.getVideoPlaybackQuality||v.paused||st.video==='off')return;const q=v.getVideoPlaybackQuality(),now=performance.now();
 const d=VX.drop;if(d.v!==v){VX.drop={v,t:q.totalVideoFrames,dr:q.droppedVideoFrames,at:now};return}
 if(now-d.at<4000)return;const tot=q.totalVideoFrames-d.t,dr=q.droppedVideoFrames-d.dr;VX.drop={v,t:q.totalVideoFrames,dr:q.droppedVideoFrames,at:now};VX.dropRate=tot>0?dr/tot:0;
 if(tot>30&&dr/tot>0.12&&!window.__msEnhNoAuto)stepDown('video dropped '+Math.round(100*dr/tot)+'% of frames')}
function loop(v){const id=++VX.cb;let lastMT=-1;
 if(v.requestVideoFrameCallback){const f=(now,md)=>{if(id!==VX.cb)return;if(lastMT>=0&&md&&md.mediaTime>lastMT){const dt=md.mediaTime-lastMT;if(dt>0&&dt<.2)VX.vfps=VX.vfps?VX.vfps*.9+(1/dt)*.1:1/dt}lastMT=md?md.mediaTime:-1;frame();v.requestVideoFrameCallback(f)};v.requestVideoFrameCallback(f)}
 else{let lt=-1;const f=()=>{if(id!==VX.cb)return;if(!document.hidden&&v.currentTime!==lt){lt=v.currentTime;frame()}requestAnimationFrame(f)};requestAnimationFrame(f)}}
let syncing=false;
async function sync(){if(syncing)return;syncing=true;try{
 const want=st.video!=='off'&&stageOn()&&!document.hidden;
 if(!want){VX.cb++;VX.vid=null;if(VX.cv)VX.cv.style.display='none';return}
 const r=await ensureR();if(!r){if(!VX.warned){VX.warned=1;say('Video enhance is not supported in this browser')}return}
 const v=curVid();if(VX.vid!==v){VX.vid=v;VX.drop={};VX.warm=VX.frames;VX.cost=[];loop(v);frame(true)}else if(VX.cv&&VX.cv.style.display==='none'){frame(true)}
 if(VX.cv)place(v);dropCheck()}finally{syncing=false}}
setInterval(sync,500);document.addEventListener('fullscreenchange',()=>setTimeout(()=>{sync();VX.vid&&frame(true)},60));addEventListener('resize',()=>{if(VX.vid)frame(true)});
document.addEventListener('visibilitychange',sync);

/* ====================================== UI ====================================== */
const CSS=`#enhp{position:fixed;inset:0;z-index:2147483000;display:none;align-items:flex-end;justify-content:center;background:#0008}
#enhp.show{display:flex}#enhp .sh{width:min(100%,460px);max-height:min(88dvh,760px);overflow:auto;overscroll-behavior:contain;background:#16161d;color:#f3f3f6;border-radius:18px 18px 0 0;padding:14px 16px calc(16px + env(safe-area-inset-bottom));font:14px/1.35 system-ui,sans-serif;box-shadow:0 -8px 40px #000a}
@media (min-width:700px) and (min-height:560px){#enhp{align-items:center}#enhp .sh{border-radius:18px}}
#enhp h3{margin:0;font-size:17px;flex:1}#enhp h4{margin:14px 0 6px;font-size:13px;letter-spacing:.4px;text-transform:uppercase;opacity:.7}
#enhp .hd{display:flex;align-items:center;gap:8px}#enhp .x{background:none;border:0;color:inherit;font-size:22px;width:40px;height:40px;cursor:pointer}
#enhp .chips{display:flex;flex-wrap:wrap;gap:6px}#enhp .chips button,#enhp .sw2{border:1px solid #fff3;background:#ffffff10;color:inherit;border-radius:999px;padding:7px 12px;font:inherit;cursor:pointer;min-height:34px}
#enhp .chips button.on,#enhp .sw2.on{background:#ff4f2b;border-color:#ff4f2b;color:#fff}
#enhp .row{display:grid;grid-template-columns:62px 1fr 46px;align-items:center;gap:8px;margin:2px 0}#enhp .row input{width:100%;accent-color:#ff4f2b;min-height:26px}#enhp .row span:last-child{text-align:right;font-variant-numeric:tabular-nums;opacity:.85;font-size:12px}
#enhp .eq{display:grid;grid-template-columns:1fr;gap:0 14px}@media (min-width:560px){#enhp .eq{grid-template-columns:1fr 1fr}}
#enhp .note{font-size:12px;opacity:.7;margin:6px 0 0}#enhp .stat{font:12px ui-monospace,monospace;opacity:.75;margin-top:6px;word-break:break-word}
#enhp .top{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}`;
let P=null;
function fmtDb(x){return (x>0?'+':'')+(+x).toFixed(1)}
function build(){if(P)return P;const s=document.createElement('style');s.id='enh-css-20261111';s.textContent=CSS;document.head.appendChild(s);
 P=document.createElement('div');P.id='enhp';P.setAttribute('role','dialog');P.setAttribute('aria-modal','true');P.setAttribute('aria-label','Enhance sound and video');
 P.innerHTML=`<div class=sh><div class=hd><h3>&#10024; Enhance</h3><button class=x data-x aria-label=Close>&times;</button></div>
 <h4>Sound</h4><div class=top><button class=sw2 data-aon aria-pressed=false>Sound enhance: Off</button><button class=sw2 data-lvl aria-pressed=false>Loudness levelling</button></div>
 <p class=note data-ios hidden>On iPhone/iPad the sound may stop when the screen locks while Enhance or Levelling is on.</p>
 <div class=chips data-pre style="margin-top:8px">${Object.keys(PRESETS).map(k=>`<button data-p=${k}>${PRESETS[k].n}</button>`).join('')}</div>
 <h4>Tone</h4><div class=row><span>Bass</span><input type=range min=-6 max=9 step=.5 data-k=bass aria-label=Bass><span></span></div>
 <div class=row><span>Clarity</span><input type=range min=-6 max=6 step=.5 data-k=clar aria-label=Clarity><span></span></div>
 <div class=row><span>Width</span><input type=range min=0 max=60 step=5 data-k=width aria-label="Stereo width"><span></span></div>
 <h4>Equalizer</h4><div class=eq>${BANDS.map((f,i)=>`<div class=row><span>${f>=1000?f/1000+' kHz':f+' Hz'}</span><input type=range min=-12 max=12 step=.5 data-b=${i} aria-label="${f} hertz"><span></span></div>`).join('')}</div>
 <h4>Video</h4><div class=chips data-vm><button data-v=off>Off</button><button data-v=sharpen>Sharpen</button><button data-v=upscale>Upscale</button></div>
 <p class=note>Sharpens or upscales low-resolution video on your device's graphics chip (AMD FSR&nbsp;1). Uses a little more battery; turns itself down if your device can't keep up.</p>
 <div class=stat data-st></div></div>`;
 document.body.appendChild(P);
 P.addEventListener('click',e=>{if(e.target===P||e.target.closest('[data-x]'))close()});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&P.classList.contains('show'))close()});
 P.querySelector('[data-aon]').onclick=()=>{setOn(!st.on)};
 P.querySelector('[data-lvl]').onclick=()=>{const b=$('norm');if(b)b.click();setTimeout(ui,30)};
 P.querySelectorAll('[data-p]').forEach(b=>b.onclick=()=>preset(b.dataset.p));
 P.querySelectorAll('[data-k]').forEach(i=>i.oninput=()=>{st[i.dataset.k]=+i.value;st.preset='custom';if(!st.on)setOn(true,true);else{save();applyAudio()}ui()});
 P.querySelectorAll('[data-b]').forEach(i=>i.oninput=()=>{st.eq[+i.dataset.b]=+i.value;st.preset='custom';if(!st.on)setOn(true,true);else{save();applyAudio()}ui()});
 P.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>setVideo(b.dataset.v));
 return P}
function setOn(on,quiet){st.on=!!on;save();if(on)ensureCtx();applyAudio();ui();if(!quiet)say(on?'Sound enhance on':'Sound enhance off')}
function preset(k){if(k==='off'){setOn(false);st.preset='off';save();ui();return}const p=PRESETS[k];if(!p)return;st.preset=k;st.eq=p.eq.slice();st.bass=p.bass;st.clar=p.clar;st.width=p.width;
 if(p.level&&typeof normOn!=='undefined'&&!normOn){const b=$('norm');b&&b.click()}setOn(true,true);say('Sound: '+p.n)}
function setVideo(m){st.video=m;VX.warm=VX.frames;VX.autoOff=null;VX.off='';VX.cost=[];save();ui();sync().then(()=>{VX.vid&&frame(true);ui()})}
function open(){const m=$('npmore');if(m&&m.classList.contains('open'))m.classList.remove('open');build();ui();P.classList.add('show');clearInterval(VX.uiT);VX.uiT=setInterval(ui,1000)}
function close(){P&&P.classList.remove('show');clearInterval(VX.uiT)}
function ui(){const b=$('enhb');if(b){b.classList.toggle('on',!!st.on||st.video!=='off');b.setAttribute('aria-pressed',String(!!st.on))}const vb=$('enhvb');if(vb){vb.textContent=st.video==='upscale'?'HD+':st.video==='sharpen'?'Sharp':'HD+';vb.style.opacity=st.video==='off'?'.6':'1';vb.title='Video enhance: '+st.video}
 if(!P||!P.classList.contains('show'))return;const on=P.querySelector('[data-aon]');on.textContent='Sound enhance: '+(st.on?'On':'Off');on.classList.toggle('on',st.on);on.setAttribute('aria-pressed',String(st.on));
 const lv=typeof normOn!=='undefined'&&!!normOn,l=P.querySelector('[data-lvl]');l.classList.toggle('on',lv);l.setAttribute('aria-pressed',String(lv));l.textContent='Loudness levelling: '+(lv?'On':'Off');
 P.querySelector('[data-ios]').hidden=!IOS;
 P.querySelectorAll('[data-p]').forEach(x=>x.classList.toggle('on',st.on?x.dataset.p===st.preset:x.dataset.p==='off'));
 P.querySelectorAll('[data-k]').forEach(i=>{if(document.activeElement!==i)i.value=st[i.dataset.k];i.nextElementSibling.textContent=i.dataset.k==='width'?st.width+'%':fmtDb(st[i.dataset.k])+' dB'});
 P.querySelectorAll('[data-b]').forEach(i=>{const v=st.eq[+i.dataset.b];if(document.activeElement!==i)i.value=v;i.nextElementSibling.textContent=fmtDb(v)});
 P.querySelectorAll('[data-v]').forEach(x=>x.classList.toggle('on',x.dataset.v===st.video));
 const S=stats(),t=[];t.push('Sound: '+(A.g?(A.g.AC.state+(st.on?', processing':', bypass')):(st.on?'starts on your next tap':'off')));
 t.push('Video: '+(st.video==='off'?'off':(S.video.path||'starting')+(S.video.active?` · ${S.video.src.join('×')} → ${S.video.out.join('×')} · ${S.video.mode} · ${S.video.fps} fps`+(S.video.gpuMs!=null?` · ${S.video.gpuMs} ms/frame`:''):' · waiting for video')));
 if(VX.autoOff)t.push('Auto: '+VX.autoOff.from+' → '+VX.autoOff.to+' ('+VX.autoOff.why+')');P.querySelector('[data-st]').textContent=t.join('\n')}
function stats(){const avg=a=>a.length?+(a.reduce((x,y)=>x+y,0)/a.length).toFixed(2):null;
 return {audio:Object.assign({ok:A.ok,err:A.err,attached:!!A.g},levels()||{}),video:{want:st.video,path:VX.path,active:!!(VX.vid&&VX.cv&&VX.cv.style.display!=='none'),mode:VX.mode||null,src:VX.src,out:VX.out,fps:VX.fps,vfps:VX.vfps?Math.round(VX.vfps):null,gpuMs:avg(VX.cost),cpuMs:avg(VX.cpu),frames:VX.frames,dropRate:VX.dropRate==null?null:+VX.dropRate.toFixed(3),autoOff:VX.autoOff||null,note:VX.note}}}
function mount(){hookAud();
 const n=$('norm');if(n&&!$('enhb')){const b=document.createElement('button');b.className='pill';b.id='enhb';b.type='button';b.title='Enhance sound and video';b.innerHTML='&#10024; Enhance';b.onclick=e=>{e.preventDefault();open()};n.after(b);
  n.addEventListener('click',()=>setTimeout(ui,30))}
 const acts=$('npacts');if(acts&&!$('enhm')){const b=document.createElement('button');b.className='ib';b.id='enhm';b.type='button';b.title='Enhance sound and video';b.setAttribute('aria-label','Enhance sound and video');b.innerHTML='&#10024;';
  b.onclick=e=>{e.preventDefault();const m=$('npmore');if(m)m.classList.remove('open');open()};acts.append(b)}
 const fs=$('fs');if(fs&&!$('enhvb')){const b=document.createElement('button');b.className='ib';b.id='enhvb';b.type='button';b.setAttribute('aria-label','Video enhance');
  b.style.cssText='background:#000a;color:#fff;height:36px;min-width:44px;padding:0 8px;font:700 12px system-ui;border-radius:8px';b.onclick=e=>{e.stopPropagation();const o=['off','sharpen','upscale'];setVideo(o[(o.indexOf(st.video)+1)%3]);say('Video: '+({off:'original',sharpen:'Sharpen',upscale:'Upscale'})[st.video])};fs.before(b)}
 ui()}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount);else mount();
if(window.__msEnhG)attach(window.__msEnhG);
addEventListener('storage',e=>{if(e.key===KEY){st=load();applyAudio();ui();sync()}});
window.MSEnh={attach,open,close,stats,setOn,preset,setVideo,get state(){return JSON.parse(JSON.stringify(st))},_vx:VX,_a:A,frame:()=>frame(true)};
})();
