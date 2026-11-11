/* Song-family matcher (shared logic mirrored in music_server.py:fam_parse/fam_same). Conservative: no edit distance,
   no transliteration, no cross-language guessing. Same family = same normalized base title AND compatible evidence. */
(function(G){
const PK=/^(official|lyric|lyrics|lyrical|audio|video|videos|song|songs|full|music|visualizer|visualiser|4k|hd|hq|1080p|720p|remaster|remastered|mv|m v|clip|with|the|new|telugu|tamil|hindi|kannada|malayalam|english|punjabi|bengali|marathi|version|\d{4}|from|movie|film|ost|soundtrack|cover|remix|live|lofi|lo fi|slowed|reverb|sped|up|acoustic|unplugged|reprise|8d|karaoke|instrumental|by|and|reverbed)$/;
const VER=/\b(cover|remix|live|lo ?fi|slowed|reverb|sped up|acoustic|unplugged|reprise|8d|karaoke|instrumental)\b/;
const N=s=>(s||'').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu,' ').trim();
const pkOnly=s=>{const w=N(s).split(' ').filter(Boolean);return w.length>0&&w.every(x=>PK.test(x))};
function famParse(title,channel,meta){meta=meta||{};let t=(title||'').normalize('NFKC').toLowerCase().replace(/[\u2018\u2019\u201c\u201d]/g,"'");let ver=VER.test(N(t)),segs=[];
 let m=t.match(/\bversion of\s+(.+)$/);if(m){ver=true;t=m[1]}
 t=t.replace(/[\(\[\{]([^\)\]\}]*)[\)\]\}]/g,(all,c)=>{const f=c.match(/^\s*from\s+["']?(.+?)["']?\s*$/);if(f){segs.push(N(f[1]));return ' '}if(VER.test(N(c)))ver=true;return pkOnly(c)?' ':all});
 let parts=t.split(/\s[|｜]\s|\|/);let head=parts.shift()||'';parts.forEach(p=>{if(!pkOnly(p))segs.push(N(p))});
 let hp=head.split(/\s[-–—]\s/).filter(p=>{if(VER.test(N(p))&&/\b(cover|remix|version|live)\b/.test(N(p))&&N(p).split(' ').length<=4){ver=true;return false}return !pkOnly(p)});
 const strip=s=>s.replace(/\s*\b(ft|feat|featuring)\b\.?.*$/,'');
 let bw=N(strip(hp.join(' - '))).split(' ');const TR=/^(lyrical|lyric|lyrics|video|audio|official|hd|4k|hq|visualizer|visualiser)$/;for(;;){const L=bw.length;if(L>2&&/^(video|audio|full|lyrical)$/.test(bw[L-2])&&bw[L-1]=='song'){bw.splice(L-2,2);continue}if(L>1&&TR.test(bw[L-1])){bw.pop();continue}break}const base=bw.join(' ');const ch=(channel||'');const gen=/\s-\s*topic\s*$/i.test(ch)||/vevo/i.test(ch);
 const art=meta.artist?N(meta.artist):(gen?N(ch.replace(/\s*-\s*topic\s*$/i,'').replace(/vevo/ig,'')):'');
 const sg=[base].concat(segs.filter(Boolean)).filter(Boolean);
 return {base,segs:sg.slice(1),ver,art,full:' '+N(title)+' ',seq:sg.join('|'),nseg:sg.length,isrc:meta.isrc||'',work:meta.mb_work||'',workRel:meta.mb_work_rel||''}}
/* Strong corroboration only. Returns 'merge' | 'unknown' | 'distinct'. Only 'merge' suppresses in radio.
   Label/uploader channel is never treated as artist; same film, same channel, cover/remix keywords are NOT evidence. */
function famRel(a,b){
 if(a.isrc&&a.isrc===b.isrc)return 'merge';
 if(a.work&&(a.work===b.work||(b.workRel&&b.workRel.split(/\W+/).includes(a.work))))return 'merge';
 if(b.work&&a.workRel&&a.workRel.split(/\W+/).includes(b.work))return 'merge';
 if(!a.base||!b.base)return 'unknown';
 if(a.base!==b.base){/* 'distinct' only when proven: same genuine artist, titles not spelling-variants, no segment-order swap */
  const sk=x=>x.replace(/[aeiou\s]/g,'').replace(/(.)\1+/g,'$1');
  if(sk(a.base)===sk(b.base))return 'unknown';
  if(a.segs.includes(b.base)||b.segs.includes(a.base))return 'unknown';
  return (a.art&&a.art===b.art)?'distinct':'unknown'}
 if(a.base.length<2)return 'unknown';
 if(a.art&&a.art===b.art)return 'merge';
 const app=(x,y)=>x.art&&x.art.length>=3&&y.full.includes(' '+x.art+' ');if(app(a,b)||app(b,a))return 'merge';
 if(a.nseg>=3&&a.seq===b.seq)return 'merge';
 return 'unknown'}
function famSame(a,b){return famRel(a,b)==='merge'}
function famSameFull(a,b){if(famSame(famParse(a.title||'',a.channel||'',a),famParse(b.title||'',b.channel||'',b)))return true;try{const fl=G.famlang;if(fl&&fl.langDubRel)return fl.langDubRel(fl.enrich(a),fl.enrich(b))==='merge'}catch(e){}return false}
function famFilter(items,seeds){const raws=(seeds||[]).filter(x=>x&&x.title),keep=[];for(const x of items){if(raws.some(s=>famSameFull(x,s)))continue;raws.push(x);keep.push(x)}return keep}
G.famParse=famParse;G.famSame=famSame;G.famRel=famRel;G.famFilter=famFilter;G.famSameFull=famSameFull;if(typeof module!=='undefined')module.exports={famParse,famSame,famRel,famFilter,famSameFull}})(typeof window!=='undefined'?window:globalThis);
