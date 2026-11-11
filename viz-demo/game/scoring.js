// Pure, deterministic scoring. Times in seconds on the AudioContext timeline.
(function(root){
const PERFECT=0.040, GOOD=0.090; // inclusive windows
const BPM=120, BEAT=60/BPM, LOOP_BEATS=16, LOOP_LEN=LOOP_BEATS*BEAT; // 8 s loop
// Authored chart (beats within loop): exact, not analysed or random.
const CHART_BEATS=[0,1,2,3,4,5,6,6.5,7,8,9,10,11,12,12.5,13,14,15];
function chart(loops){const t=[];for(let l=0;l<loops;l++)for(const b of CHART_BEATS)t.push(+(l*LOOP_LEN+b*BEAT).toFixed(6));return t;}
function judge(dt){const a=Math.abs(dt);if(a<=PERFECT+1e-9)return'perfect';if(a<=GOOD+1e-9)return'good';return null;}
// calibrationMs: positive = player's taps register LATE (output/input latency); we subtract it.
function createGame(notes,calibrationMs=0){
  return {notes:notes.map(t=>({t,hit:null})),score:0,counts:{perfect:0,good:0,miss:0},combo:0,
  tap(songTime){const t=songTime-calibrationMs/1000;let best=null,bd=Infinity;
    for(const n of this.notes){if(n.hit)continue;const d=Math.abs(t-n.t);if(d<bd){bd=d;best=n}}
    if(!best)return{result:'none'};const r=judge(t-best.t);if(!r)return{result:'stray'};
    best.hit=r;this.counts[r]++;this.combo++;this.score+=r==='perfect'?300:100;return{result:r,note:best.t,dt:t-best.t};},
  // Called with current song time from any frame rate; marks notes past the window as missed.
  update(songTime){const t=songTime-calibrationMs/1000;const out=[];
    for(const n of this.notes)if(!n.hit&&t-n.t>GOOD+1e-9){n.hit='miss';this.counts.miss++;this.combo=0;out.push(n.t)}return out;}};
}
const api={PERFECT,GOOD,BPM,BEAT,LOOP_LEN,CHART_BEATS,chart,judge,createGame};
if(typeof module!=='undefined')module.exports=api;else root.Rhythm=api;
})(this);
