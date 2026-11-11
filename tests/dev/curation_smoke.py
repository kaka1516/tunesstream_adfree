"""Smoke /api/radio with fake ta/lk/sk; prints why + channel. Reads MUSIC_KEY from env or music.env (never printed)."""
import json, os, sys, urllib.parse, urllib.request, pathlib, re
k = os.environ.get("MUSIC_KEY")
if not k and pathlib.Path("music.env").exists():
    m = re.search(r"^MUSIC_KEY=(.*)$", pathlib.Path("music.env").read_text(), re.M); k = m and m.group(1).strip().strip('"')
port = os.environ.get("MUSIC_PORT", "8120"); vid = sys.argv[1] if len(sys.argv) > 1 else "dQw4w9WgXcQ"
lk = sys.argv[2] if len(sys.argv) > 2 else ""
q = urllib.parse.urlencode({"k": k or "", "id": vid, "ta": "", "sk": "", "lk": lk, "mix": "balanced"})
L = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/radio?{q}", timeout=180))
for i, x in enumerate(L[:25]): print(f"{i:2} {x.get('why','?'):15} {x.get('channel','')[:28]:28} {x.get('title','')[:50]}")
print("items", len(L), "missing_why", sum(1 for x in L if not x.get("why")))
