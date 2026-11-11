const R=require('./scoring.js'),assert=require('assert');let n=0;const ok=(c,m)=>{assert(c,m);n++;console.log('ok',m)};
ok(R.judge(0)==='perfect','0ms perfect');ok(R.judge(0.040)==='perfect','+40ms perfect');ok(R.judge(-0.040)==='perfect','-40ms perfect');
ok(R.judge(0.041)==='good','+41ms good');ok(R.judge(0.090)==='good','+90ms good');ok(R.judge(-0.090)==='good','-90ms good');
ok(R.judge(0.091)===null,'+91ms not hit');ok(R.judge(-0.091)===null,'-91ms not hit');
let g=R.createGame([1,1.5]);ok(g.tap(1.01).note===1,'nearest unhit');ok(g.tap(1.01).result==='stray','same note not hit twice (1.5 too far)');
g=R.createGame([1,1.1]);g.tap(1.05);ok(g.tap(1.05).note===1.1,'second tap goes to next unhit');
g=R.createGame([1]);ok(g.tap(1.3).result==='stray','stray tap no score');ok(g.score===0,'stray zero score');
g=R.createGame([1],50);ok(g.tap(1.05).result==='perfect','calibration +50ms shifts late tap to perfect');
g=R.createGame([1],-50);ok(g.tap(0.95).result==='perfect','calibration -50ms shifts early tap');
// fps independence: same taps, different update rates -> identical outcome
function run(fps){const g=R.createGame(R.chart(2));const taps=g.notes.map((x,i)=>x.t+[0,0.03,-0.06,0.2][i%4]);let ti=0;
 for(let t=0;t<=17;t+=1/fps){while(ti<taps.length&&taps[ti]<=t){g.tap(taps[ti]);ti++}g.update(t)}g.update(99);return JSON.stringify([g.score,g.counts]);}
const a=run(30),b=run(60),c=run(144),d=run(7);ok(a===b&&b===c&&c===d,'fps independent 7/30/60/144: '+a);
ok(R.chart(1).length===18&&R.LOOP_LEN===8,'chart authored 18 notes / 8s loop');
console.log(`ALL ${n} PASSED`);
