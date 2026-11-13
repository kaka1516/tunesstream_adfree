import os, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ms_headcache as H

class HeadCacheTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.c = H.HeadCache(Path(self.td.name) / "heads", max_bytes=800, head_bytes=200)

    def tearDown(self):
        self.td.cleanup()

    def test_put_get_and_corrupt_fallback(self):
        self.assertIsNone(self.c.get("aaaaaaaaaaa", "std"))
        data = b"A" * 100
        self.assertTrue(self.c.put("aaaaaaaaaaa", "std", data, size=5000, ctype="audio/mp4"))
        hit = self.c.get("aaaaaaaaaaa", "std")
        self.assertEqual(hit["data"], data)
        self.assertEqual(hit["size"], 5000)
        self.assertEqual(hit["ctype"], "audio/mp4")
        # corrupt the sidecar -> get returns None (caller must fall back)
        p = self.c.paths("aaaaaaaaaaa", "std")[1]
        p.write_text("{bad")
        self.assertIsNone(self.c.get("aaaaaaaaaaa", "std"))

    def test_lru_evict(self):
        self.c.put("bbbbbbbbbbb", "std", b"B" * 300, size=3000)
        self.c.put("ccccccccccc", "std", b"C" * 300, size=3000)
        self.c.put("ddddddddddd", "std", b"D" * 300, size=3000)
        # cap is 800 bytes; first (oldest) should go
        self.assertIsNone(self.c.get("bbbbbbbbbbb", "std"))
        self.assertIsNotNone(self.c.get("ddddddddddd", "std"))
        st = self.c.stats()
        self.assertLessEqual(st["bytes"], 800)

    def test_put_does_not_shrink(self):
        self.assertTrue(self.c.put("v1", "std", b"A" * 100, 1000, "audio/mp4"))
        self.assertTrue(self.c.put("v1", "std", b"B" * 400, 1000, "audio/mp4"))
        got = self.c.get("v1", "std")
        self.assertEqual(got["n"], 400)
        self.assertEqual(got["data"][:1], b"B")
        self.assertTrue(self.c.put("v1", "std", b"C" * 100, 1000, "audio/mp4"))
        got = self.c.get("v1", "std")
        self.assertEqual(got["n"], 400)
        self.assertEqual(got["data"][:1], b"B")

    def test_itag_and_size_must_match(self):
        data = b"H" * 80
        self.assertTrue(self.c.put("eeeeeeeeeee", "std", data, 4000, "audio/mp4", itag="140"))
        # same itag + size -> hit
        hit = self.c.get("eeeeeeeeeee", "std", itag="140", size=4000)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["itag"], "140")
        self.assertEqual(hit["data"], data)
        # different itag or size -> miss (do not stitch a different format)
        self.assertIsNone(self.c.get("eeeeeeeeeee", "std", itag="251", size=4000))
        self.assertIsNone(self.c.get("eeeeeeeeeee", "std", itag="140", size=9999))
        # legacy untagged entry is rejected when the caller supplies an itag
        self.c.put("fffffffffff", "std", b"L" * 80, 4000, "audio/webm")  # no itag
        self.assertIsNotNone(self.c.get("fffffffffff", "std"))
        self.assertIsNone(self.c.get("fffffffffff", "std", itag="251"))

        # putting a tagged intro over a same-size legacy entry must store the itag
        # (otherwise get(itag=...) keeps missing and the head cache is dead)
        self.c.put("ggggggggggg", "std", b"G" * 80, 4000, "audio/mp4")  # legacy
        self.assertIsNone(self.c.get("ggggggggggg", "std", itag="140"))
        self.assertTrue(self.c.put("ggggggggggg", "std", b"G" * 80, 4000, "audio/mp4", itag="140"))
        hit = self.c.get("ggggggggggg", "std", itag="140", size=4000)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["itag"], "140")

if __name__ == "__main__":
    unittest.main()
