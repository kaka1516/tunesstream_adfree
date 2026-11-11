/* Visuals catalog hook: load rev.js (cache-bust) and VRM index (MilkDrop presets removed 2026-11-11).
   Safe no-ops if a file is missing. The song keeps playing if this fails. */
(function(){
  function load(src){
    return new Promise(function(res){
      var s=document.createElement('script');
      s.src=src; s.async=true;
      s.onload=function(){res(true)}; s.onerror=function(){res(false)};
      document.head.appendChild(s);
    });
  }
  window.__msLoadVizCatalog=async function(){
    try{
      var t=Date.now();
      await load('/assets/viz/rev.js?t='+t);
      var v=window.__MS_VIZ_REV||('t'+t);
      /* notrippy-20261111: Trippy (MilkDrop) removed; extra presets are no longer loaded */
      try{
        var r=await fetch('/assets/chars/vrm/index.json?v='+encodeURIComponent(v),{cache:'no-store'});
        if(r.ok){
          var j=await r.json();
          if(j&&Array.isArray(j.models)) window.__MS_VRM_INDEX=j.models;
        }
      }catch(_){}
      // adult-viz-20261111: 18+ characters stay in a separate index and are merged only when the flag is on.
      try{
        var adultOn=typeof window.__msAdultViz==='function'&&window.__msAdultViz();
        if(adultOn){
          var ra=await fetch('/assets/chars/vrm/adult/index.json?v='+encodeURIComponent(v),{cache:'no-store'});
          if(ra.ok){
            var ja=await ra.json();
            if(ja&&Array.isArray(ja.models)&&ja.models.length){
              window.__MS_VRM_ADULT=ja.models;
              window.__MS_VRM_INDEX=(window.__MS_VRM_INDEX||[]).concat(ja.models);
            }
          }
        }
      }catch(_){}
      return window.__MS_VIZ_REV||'';
    }catch(e){return ''}
  };
})();
