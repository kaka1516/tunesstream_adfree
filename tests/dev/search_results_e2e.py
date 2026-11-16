#!/usr/bin/env python3
"""Search results show a full (wrapped) title plus date and duration on 10 rows.
Mobile and desktop layouts. Never prints secrets. Does not play audio.
"""
import json, os, re, time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = os.environ.get("MS_BASE", "https://tunestream.dpdns.org")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
QUERY = os.environ.get("MS_SEARCH_Q", "Arijit Singh")
R = []

def pw():
    return Path(os.environ.get("MS_PW_FILE", "/tmp/loadtest.pw")).read_text(encoding="utf-8").strip()

def ok(name, cond, info=None):
    R.append({"name": name, "pass": bool(cond), "detail": info})
    print(("PASS " if cond else "FAIL ") + name, json.dumps(info, default=str)[:900] if info is not None else "")

DATE_RE = re.compile(
    r"(ago|premiered|streamed|uploaded|\b20\d{2}\b|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4}-\d{2}-\d{2})",
    re.I,
)
DUR_RE = re.compile(r"\b\d+:\d{2}\b")

def login(page):
    page.goto(BASE + "/login", wait_until="domcontentloaded", timeout=45000)
    st = page.evaluate(
        """async ({u,p}) => {
          const r = await fetch('/api/auth/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({u,p}), credentials:'same-origin'});
          return {ok:r.ok, status:r.status};
        }""",
        {"u": "loadtest", "p": pw()},
    )
    if not st or not st.get("ok"):
        raise SystemExit(f"login failed {st}")
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
    page.wait_for_function("() => typeof search === 'function' && typeof render === 'function'", timeout=30000)
    try:
        page.locator("#resume20 button[data-x]").first.click(timeout=1500)
    except Exception:
        pass
    page.evaluate("() => { try { const b=document.querySelector('#resume20'); if(b) b.remove(); } catch(e) {} }")

def api_search(page, q, n=20):
    return page.evaluate(
        """async ({q,n}) => {
          const r = await fetch('/api/search?q='+encodeURIComponent(q)+'&n='+n, {credentials:'same-origin', cache:'no-store'});
          const j = await r.json().catch(()=>[]);
          return {st:r.status, rows:j};
        }""",
        {"q": q, "n": n},
    )

def run_search(page, q):
    page.evaluate(
        """(q) => {
          try { if (typeof radOn!=='undefined') { radOn=false; try{tog('rad',false)}catch(e){} } } catch(e) {}
          try { document.getElementById('np').classList.remove('open'); } catch(e) {}
          try { hideHome(); } catch(e) {}
          const inp=document.getElementById('q');
          if (inp) { inp.value=q; const qx=document.getElementById('qx'); if(qx) qx.style.display='block'; }
          search(q);
        }""",
        q,
    )
    page.wait_for_function(
        """() => {
          const list=document.getElementById('list');
          if (!list || !list.classList.contains('res')) return false;
          return list.querySelectorAll('li').length >= 10;
        }""",
        timeout=45000,
    )
    # allow lazy-fill of date/views
    t0 = time.time()
    while time.time() - t0 < 6:
        info = inspect(page)
        vids = [r for r in (info.get("rows") or []) if r.get("isVideo")]
        dated = sum(1 for r in vids[:10] if r.get("hasDate"))
        if dated >= 8:
            break
        time.sleep(0.4)
    return inspect(page)

def inspect(page):
    return page.evaluate(
        """() => {
          const list=document.getElementById('list');
          const rows=[...list.querySelectorAll('li')].map((li,i) => {
            const t=li.querySelector('.t');
            const s=li.querySelector('.s');
            const mdt=li.querySelector('.mdt');
            const mds=li.querySelector('.mds');
            const cs=t?getComputedStyle(t):null;
            const title=(t&&t.innerText||'').replace(/^\\s*(OFFLINE|SHORTS|MIX|PLAYLIST)\\s*/,' ').trim();
            const raw=(t&&t.textContent||'').trim();
            const sub=s?s.innerText:'';
            const ws=cs&&cs.whiteSpace;
            const to=cs&&cs.textOverflow;
            const clamp=cs&&(cs.webkitLineClamp||'');
            const cut = ws==='nowrap' && to==='ellipsis' && t && (t.scrollWidth > t.clientWidth+1);
            const rec=(typeof res!=='undefined'&&res[i])||{};
            return {
              i, title, raw, sub, apiTitle: rec.title||'', apiDur: rec.dur||null,
              ago: rec.ago||'', uploaded: rec.uploaded||'', ts: rec.ts||null,
              views: rec.views, views_t: rec.views_t||'',
              channel: rec.channel||'',
              isVideo: !!(rec.id && !rec.list),
              isList: !!rec.list,
              whiteSpace: ws, textOverflow: to, lineClamp: String(clamp),
              ellipsisCut: !!cut, nowrap: ws==='nowrap',
              scrollW: t?t.scrollWidth:0, clientW: t?t.clientWidth:0, clientH: t?t.clientHeight:0,
              menuTitle: mdt?mdt.textContent.trim():'',
              menuDetail: mds?mds.innerText:'',
              hasDur: /\\b\\d+:\\d{2}\\b/.test(sub),
              hasDate: /(ago|premiered|streamed|uploaded|\\b20\\d{2}\\b|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\\d{4}-\\d{2}-\\d{2})/i.test(sub)
            };
          });
          const meta=document.querySelector('meta[name=ms-build]');
          return {build: meta&&meta.content||'', sw: window.__swV||'', n: rows.length, listRes: list.classList.contains('res'), rows};
        }"""
    )

def open_menu(page, idx=0):
    page.evaluate(
        """(i) => {
          const b=document.querySelectorAll('#list.res li button[data-m]')[i];
          if (b) b.click();
        }""",
        idx,
    )
    page.wait_for_function(
        """(i) => { const m=document.getElementById('m'+i); return !!(m && m.classList.contains('open')); }""",
        arg=idx,
        timeout=5000,
    )

def check_layout(page, label):
    api = api_search(page, QUERY, 20)
    ok(f"{label} /api/search 200", api.get("st") == 200, {"st": api.get("st"), "n": len(api.get("rows") or [])})
    rows = api.get("rows") or []
    vids_api = [r for r in rows if r.get("id") and not r.get("list")]
    ok(f"{label} api has 10 video results", len(vids_api) >= 10, {"n": len(vids_api)})
    with_meta = sum(1 for r in vids_api if r.get("dur") and (r.get("ago") or r.get("uploaded") or r.get("ts")))
    ok(f"{label} api date+duration on most", with_meta >= 8, {"with_meta": with_meta, "sample": [
        {k: v for k, v in r.items() if k in ("title", "dur", "ago", "uploaded", "ts", "views", "views_t", "channel")}
        for r in vids_api[:3]
    ]})

    info = run_search(page, QUERY)
    ok(f"{label} build ms-v*", (info.get("build") or "").startswith("ms-v"), {"build": info.get("build"), "sw": info.get("sw")})
    ok(f"{label} list has res class", info.get("listRes") is True, {"listRes": info.get("listRes")})
    rows_ui = info.get("rows") or []
    vids = [r for r in rows_ui if r.get("isVideo")]
    ok(f"{label} 10 video rows rendered", len(vids) >= 10, {"n": len(vids), "total": len(rows_ui)})
    take = vids[:10]
    titles_ok = []
    cuts = []
    for r in take:
        api_t = (r.get("apiTitle") or "").strip()
        shown = (r.get("title") or "").strip()
        raw = r.get("raw") or ""
        full = bool(api_t) and (api_t in raw or api_t == shown)
        titles_ok.append(full)
        if r.get("ellipsisCut") or r.get("nowrap"):
            cuts.append({"i": r["i"], "nowrap": r.get("nowrap"), "cut": r.get("ellipsisCut"), "ws": r.get("whiteSpace"), "to": r.get("textOverflow")})
    ok(f"{label} full titles on 10 results", all(titles_ok) and len(titles_ok) == 10, {
        "ok": sum(titles_ok), "samples": [{"shown": r.get("title"), "api": r.get("apiTitle"), "clamp": r.get("lineClamp")} for r in take[:3]]
    })
    ok(f"{label} titles wrap (no nowrap ellipsis cut)", not cuts, {"cuts": cuts, "clamp": take[0].get("lineClamp") if take else None, "ws": take[0].get("whiteSpace") if take else None})
    n_dur = sum(1 for r in take if r.get("hasDur") or r.get("apiDur"))
    n_date = sum(1 for r in take if r.get("hasDate") or r.get("ago") or r.get("uploaded") or r.get("ts"))
    ok(f"{label} duration on 10 results", n_dur >= 8, {"n_dur": n_dur, "subs": [r.get("sub") for r in take[:5]]})
    ok(f"{label} date on 10 results", n_date >= 8, {"n_date": n_date, "subs": [r.get("sub") for r in take[:5]]})

    # ⋯ menu shows full untruncated title + details
    try:
        open_menu(page, take[0]["i"] if take else 0)
        det = page.evaluate(
            """(i) => {
              const m=document.getElementById('m'+i);
              const t=m&&m.querySelector('.mdt');
              const d=m&&m.querySelector('.mds');
              const cs=t&&getComputedStyle(t);
              return {open:!!(m&&m.classList.contains('open')),
                      title:t?t.textContent.trim():'', detail:d?d.innerText:'',
                      nowrap:cs&&cs.whiteSpace==='nowrap', ellipsis:cs&&cs.textOverflow==='ellipsis'};
            }""",
            take[0]["i"] if take else 0,
        )
    except Exception as e:
        det = {"err": type(e).__name__}
    api_t = (take[0].get("apiTitle") if take else "") or ""
    ok(f"{label} more-menu full title", bool(det.get("open")) and api_t and api_t in (det.get("title") or "") and not det.get("nowrap"),
       {"det": det, "api": api_t})
    detail = det.get("detail") or ""
    ok(f"{label} more-menu has date+duration", bool(DUR_RE.search(detail)) and bool(DATE_RE.search(detail)), {"detail": detail[:300]})
    # close menu
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass

def launch(p, desktop):
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
          if desktop else
          "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
    vp = {"width": 1280, "height": 800} if desktop else {"width": 390, "height": 844}
    browser = p.chromium.launch(executable_path=CHROME, headless=True,
        args=["--autoplay-policy=no-user-gesture-required", "--disable-dev-shm-usage"])
    ctx = browser.new_context(viewport=vp, user_agent=ua)
    page = ctx.new_page()
    return browser, page

def main():
    only = os.environ.get("LAYOUT", "both")
    layouts = []
    if only in ("both", "mobile"):
        layouts.append(False)
    if only in ("both", "desktop"):
        layouts.append(True)
    with sync_playwright() as p:
        for desktop in layouts:
            label = "desktop" if desktop else "mobile"
            browser, page = launch(p, desktop)
            try:
                login(page)
                check_layout(page, label)
            finally:
                browser.close()
    failed = [x for x in R if not x["pass"]]
    print("RESULT", json.dumps({"passed": sum(1 for x in R if x["pass"]), "failed": len(failed), "total": len(R)}))
    raise SystemExit(1 if failed else 0)

if __name__ == "__main__":
    main()
