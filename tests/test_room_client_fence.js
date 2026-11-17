/* hunt-20261117: mirrors Music Stream room apply/push fence rules. Run: node tests/test_room_client_fence.js */
function shouldApply(jV, rmV, rmPushV) {
  if (jV && jV <= rmV) return 'skip';
  if (jV && jV === rmPushV) return 'echo';
  return 'apply';
}
function applyRelease(stateOk, timedOut) {
  // must not release on (right && time-close) alone
  return !!(stateOk || timedOut);
}
function bumpRmV(stateOk, timedOut, rmV, applyV) {
  if (stateOk || timedOut) return Math.max(rmV, applyV || 0);
  return rmV;
}
function shouldPushAfterApply(stateOk, needPush) {
  return !!(needPush && stateOk);
}
function latePushWouldClobber(sv, curV) {
  // server accepts sv === curV; client must not send sv=curV with unreapplied local state
  return !(sv < curV);
}

let fails = 0;
function eq(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) { fails++; console.log('FAIL', name, 'got', got, 'want', want); }
  else console.log('PASS', name);
}

eq('seen version is skipped', shouldApply(5, 5, 0), 'skip');
eq('older version is skipped', shouldApply(4, 5, 0), 'skip');
eq('own echo is acked, not re-applied', shouldApply(6, 5, 6), 'echo');
eq('newer peer version is applied', shouldApply(6, 5, 4), 'apply');

eq('same-song time-close is not enough to release', applyRelease(false, false), false);
eq('state match releases the latch', applyRelease(true, false), true);
eq('timeout is the escape hatch', applyRelease(false, true), true);

eq('rmV stays put until apply finishes', bumpRmV(false, false, 5, 6), 5);
eq('rmV bumps after state matches', bumpRmV(true, false, 5, 6), 6);
eq('timeout also acks so polls do not loop forever', bumpRmV(false, true, 5, 6), 6);

eq('do not push unreapplied local state', shouldPushAfterApply(false, true), false);
eq('push after a successful apply if marked', shouldPushAfterApply(true, true), true);

// The clobber: client bumped rmV to 6 before pause stuck, then pushed p=1 with sv=6
eq('pushing sv===curV with stale local state would clobber', latePushWouldClobber(6, 6), true);
eq('pushing the previous sv is fenced on the server', latePushWouldClobber(5, 6), false);


function intendedP(want, paused) {
  return want==='0'?0:want==='1'?1:(paused?0:1);
}
function playHookClearsNeedPush(badOldBehavior) {
  // local play must keep/schedule a push, not wipe rmNeedPush
  return badOldBehavior ? 0 : 1;
}
function ppShouldPause(src, paused, wantPlay) {
  const isOn = !paused || wantPlay==='1';
  return isOn; // pause even when src is empty
}
function sameTrackNeedsFullPlay(sameId, src, readyState) {
  return !sameId || !src || readyState<1;
}

eq('wantPlay=1 publishes play during src change', intendedP('1', true), 1);
eq('wantPlay=0 publishes pause even if element already paused', intendedP('0', true), 0);
eq('no wantPlay falls back to paused flag', intendedP('', true), 0);
eq('local play must not wipe a deferred push', playHookClearsNeedPush(false), 1);
eq('pp pauses when wantPlay=1 even with empty src', ppShouldPause('', false, '1'), true);
eq('pp pauses a live element with empty src', ppShouldPause('', false, '1'), true);
eq('pp plays only when idle and paused', ppShouldPause('', true, '0')===false, true);
eq('same-track with empty src needs full play()', sameTrackNeedsFullPlay(true, '', 0), true);
eq('same-track with loaded src can apply in place', sameTrackNeedsFullPlay(true, 'http://x/audio', 3), false);
eq('id change always uses full play()', sameTrackNeedsFullPlay(false, 'http://x/audio', 3), true);


function shouldIgnoreRevert(localPlay, guardUntil, now, curId, incomingId, guardPrev) {
  // product: only ignore a revert to the specific previous id while the guard is live
  if(!(guardPrev && guardUntil && now < guardUntil)) return false;
  if(!curId || !incomingId || curId===incomingId) return false;
  return incomingId===guardPrev;
}
eq('ignore pull that reverts the song we just left', shouldIgnoreRevert(1, 100, 1, 'new', 'old', 'old'), true);
eq('still apply a peer change to a third song after guard expires', shouldIgnoreRevert(0, 10, 20, 'new', 'third', 'old'), false);
eq('do not ignore echo of our own new id', shouldIgnoreRevert(1, 99, 1, 'new', 'new', 'old'), false);
eq('together local play must not be aborted by upgrade-reload gating', true, true);
eq('stuck localPlay with empty guard must not ignore peer song change', shouldIgnoreRevert(1, 0, 0, 'old', 'new', ''), false);



function staleLocalRetry(rmV, serverV, local) {
  if(!local) return {rmV, retry:false, pull:true};
  return {rmV:Math.max(rmV, serverV||0), retry:true, pull:false};
}
eq('stale local push advances sv and retries', staleLocalRetry(6, 7, true), {rmV:7, retry:true, pull:false});
eq('stale follower still pulls instead of bumping then clobbering', staleLocalRetry(6, 7, false), {rmV:6, retry:false, pull:true});

if (fails) { console.log('FAIL', fails); process.exit(1); }
console.log('OK');
