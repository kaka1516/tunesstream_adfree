/* Music Stream rhythm game loader (ms-v80).
 * The game itself is Neolution by GareBear99 — https://github.com/GareBear99/Neolution — MIT License
 * (copy + licence in /vendor/neolution/, our changes marked "MS:" in game.html). It runs in a same-origin iframe and
 * plays along with the song already playing here: notes come from onset detection on that same track.
 * Replaces the msgame-* mini games (old file kept as game.pre-v80.js).
 * Contract with player.html: window.MSGame = { open(ctx), close(), isOpen() }; ctx = { audio, analyser(), colors(), toggle(), next(), close() } */
(function () {
  'use strict';
  if (window.MSGame && window.MSGame.__neo) return;
  var wrap = null, frame = null, ctxRef = null, prevFocus = null;
  function curTrack() { try { return typeof cur === 'function' ? cur() : null; } catch (e) { return null; } }
  window.__msGameHost = {
    audio: function () { try { if (typeof AUD !== 'undefined' && AUD) return AUD; } catch (e) {} return document.getElementById('aud') || (ctxRef && ctxRef.audio); },
    ctx: function () { try { return typeof AC !== 'undefined' ? AC : null; } catch (e) { return null; } },
    analyser: function () { try { return ctxRef && ctxRef.analyser ? ctxRef.analyser() : (window.__msAnalyser ? window.__msAnalyser() : null); } catch (e) { return null; } },
    trackKey: function () { var t = curTrack(); return t && t.id ? String(t.id) : ''; },
    title: function () { var t = curTrack(); return t ? String(t.title || '') : ''; },
    toggle: function () { try { ctxRef && ctxRef.toggle ? ctxRef.toggle() : document.getElementById('pp').click(); } catch (e) {} },
    close: function () { api.close(); }
  };
  function onKey(e) { if (e.key === 'Escape' && wrap) { e.preventDefault(); api.close(); } }
  var api = {
    __neo: true,
    open: function (ctx) {
      ctxRef = ctx || null;
      if (wrap) { wrap.hidden = false; try { frame.focus(); } catch (e) {} return; }
      prevFocus = document.activeElement;
      wrap = document.createElement('div'); wrap.id = 'msneo';
      wrap.setAttribute('role', 'dialog'); wrap.setAttribute('aria-label', 'Rhythm game');
      wrap.style.cssText = 'position:fixed;inset:0;z-index:2147483000;background:#000';
      frame = document.createElement('iframe');
      frame.title = 'Neolution rhythm game'; frame.src = '/vendor/neolution/game.html?v=80';
      frame.allow = 'autoplay; fullscreen; gamepad';
      frame.style.cssText = 'border:0;width:100%;height:100%;display:block';
      wrap.appendChild(frame); document.body.appendChild(wrap);
      frame.addEventListener('load', function () { try { frame.focus(); } catch (e) {} });
      document.addEventListener('keydown', onKey, true);
    },
    close: function () {
      if (!wrap) return;
      document.removeEventListener('keydown', onKey, true);
      try { wrap.remove(); } catch (e) {}
      wrap = null; frame = null;
      try { ctxRef && ctxRef.close && ctxRef.close(); } catch (e) {}
      try { prevFocus && prevFocus.focus && prevFocus.focus(); } catch (e) {}
    },
    isOpen: function () { return !!wrap; },
    frame: function () { return frame; }
  };
  window.MSGame = api;
})();
