"""playlists-20261116: locked per-user playlist ops + old lpl migration. No network, no secrets."""
from __future__ import annotations
import json, os, sys, tempfile, threading, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ms_users as U

SONGS = [
    {"id": "4NRXx6U8ABQ", "title": "A", "channel": "X", "dur": 10},
    {"id": "dQw4w9WgXcQ", "title": "B", "channel": "Y", "dur": 20},
    {"id": "jNQXAC9IVRw", "title": "C", "channel": "Z", "dur": 30},
]

def store():
    d = Path(tempfile.mkdtemp(prefix="ms_pl_"))
    st = U.Store(d)
    ok, e = st.create("alice", "password12", "user")
    assert ok, e
    return st, d

def test_crud_and_migrate():
    st, d = store()
    # migrate old {name, ids} lpl
    path = st.state_path("alice")
    st.udir()
    U._atomic_write(path, {"rev": 1, "ts": time.time(), "ls": {"lpl": json.dumps([{"name": "Old", "ids": ["4NRXx6U8ABQ"]}])}, "now": None}, secure=False)
    pls = st.list_playlists("alice")
    assert len(pls) == 1 and pls[0]["name"] == "Old" and pls[0]["songs"][0]["id"] == "4NRXx6U8ABQ"
    assert pls[0]["id"].startswith("p_")

    ok, rv = st.playlist_op("alice", {"op": "create", "name": "Gym", "songs": SONGS})
    assert ok, rv
    gym = rv["playlist"]
    assert gym["name"] == "Gym" and [s["id"] for s in gym["songs"]] == [s["id"] for s in SONGS]

    ok, rv = st.playlist_op("alice", {"op": "rename", "id": gym["id"], "name": "Lift"})
    assert ok and rv["playlist"]["name"] == "Lift"

    ok, rv = st.playlist_op("alice", {"op": "reorder", "id": gym["id"], "from": 0, "to": 2})
    assert ok, rv
    ids = [s["id"] for s in rv["playlist"]["songs"]]
    assert ids == ["dQw4w9WgXcQ", "jNQXAC9IVRw", "4NRXx6U8ABQ"], ids

    ok, rv = st.playlist_op("alice", {"op": "remove", "id": gym["id"], "index": 1})
    assert ok and [s["id"] for s in rv["playlist"]["songs"]] == ["dQw4w9WgXcQ", "4NRXx6U8ABQ"]

    ok, rv = st.playlist_op("alice", {"op": "add", "id": gym["id"], "songs": [SONGS[2]]})
    assert ok and rv["playlist"]["songs"][-1]["id"] == "jNQXAC9IVRw"

    ok, rv = st.playlist_op("alice", {"op": "add", "id": gym["id"], "songs": [SONGS[2]]})
    assert not ok and "already" in str(rv)

    # persist across a new Store (simulates another worker)
    st2 = U.Store(d)
    pls2 = st2.list_playlists("alice")
    names = {p["name"] for p in pls2}
    assert "Lift" in names and "Old" in names
    lift = next(p for p in pls2 if p["name"] == "Lift")
    assert [s["id"] for s in lift["songs"]] == ["dQw4w9WgXcQ", "4NRXx6U8ABQ", "jNQXAC9IVRw"]

    ok, rv = st2.playlist_op("alice", {"op": "delete", "id": lift["id"]})
    assert ok
    assert all(p["name"] != "Lift" for p in st.list_playlists("alice"))

    ok, rv = st.playlist_op("nobody", {"op": "create", "name": "X"})
    assert not ok

    ok, rv = st.playlist_op("alice", {"op": "nope"})
    assert not ok

def test_file_lock_serialized_creates():
    st, d = store()
    err = []
    def worker(n):
        try:
            ok, rv = st.playlist_op("alice", {"op": "create", "name": f"P{n}"})
            if not ok:
                err.append(rv)
        except Exception as e:
            err.append(str(e))
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in ts: t.start()
    for t in ts: t.join()
    assert not err, err
    pls = U.Store(d).list_playlists("alice")
    assert len(pls) == 12, len(pls)
    assert len({p["id"] for p in pls}) == 12

if __name__ == "__main__":
    test_crud_and_migrate()
    test_file_lock_serialized_creates()
    print("test_playlists OK")
