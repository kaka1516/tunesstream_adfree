"""v113: media-byte validation and a fallback ladder that actually changes format.

The 11:46 IST skip storm on Android 10 Chrome/PWA (MEDIA_ERR_SRC_NOT_SUPPORTED)
failed fb=1,2,3 because fb=1 re-requested q=std with no fresh=1, and fb=3 /stream
was rewritten to /audio?q=std whenever Chrome sent Range.

Never prints keys. Run: python3 tests/test_audio_fallback.py
"""
import os, sys, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Importing music_server reads music.env if present; tests never print it.
import music_server as ms

FTYP = b"\x00\x00\x00\x18ftypdash" + b"\x00" * 32
WEBM = b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81" + b"\x00" * 32
MP3 = b"ID3\x04\x00\x00\x00\x00\x00" + b"\x00" * 32
MP3_SYNC = bytes([0xFF, 0xFB]) + b"\x00" * 32
HTML = b"<!DOCTYPE html><html>login required</html>"
JSON = b'{"error":"expired","error_code":"403"}'
XML = b"<?xml version='1.0'?><Error>AccessDenied</Error>"
PLAIN = b"login required"


class MediaBytesTest(unittest.TestCase):
    def test_kinds_accept_real_media(self):
        self.assertEqual(ms._media_kind(FTYP, "audio/mp4"), "mp4")
        self.assertEqual(ms._media_kind(WEBM, "audio/webm"), "webm")
        self.assertEqual(ms._media_kind(MP3, "audio/mpeg"), "mp3")
        self.assertEqual(ms._media_kind(MP3_SYNC, "audio/mpeg"), "mp3")
        self.assertTrue(ms._media_bytes_ok(FTYP, "audio/mp4"))
        self.assertTrue(ms._media_bytes_ok(WEBM, "audio/webm"))

    def test_rejects_error_bodies_even_if_ctype_claims_audio(self):
        for body in (HTML, JSON, XML, PLAIN, b""):
            self.assertIsNone(ms._media_kind(body, "audio/mp4"), body[:20])
            self.assertFalse(ms._media_bytes_ok(body, "audio/mp4"), body[:20])
        self.assertFalse(ms._media_bytes_ok(HTML, "text/html"))
        self.assertFalse(ms._media_bytes_ok(JSON, "application/json"))


class StreamRewriteTest(unittest.TestCase):
    def test_range_rewrites_to_std_audio_by_default(self):
        self.assertTrue(ms._stream_rewrite_to_audio("bytes=0-", {}, have_ffmpeg=True))
        self.assertTrue(ms._stream_rewrite_to_audio("bytes=0-65535", {}, have_ffmpeg=True))
        self.assertTrue(ms._stream_rewrite_to_audio(None, {}, have_ffmpeg=False))
        self.assertFalse(ms._stream_rewrite_to_audio(None, {}, have_ffmpeg=True))

    def test_fmt_mp3_keeps_stream_even_with_range(self):
        self.assertTrue(ms._stream_force_mp3({"fmt": "mp3"}))
        self.assertTrue(ms._stream_force_mp3({"compat": "1"}))
        self.assertFalse(ms._stream_force_mp3({}))
        self.assertFalse(ms._stream_rewrite_to_audio("bytes=0-", {"fmt": "mp3"}, have_ffmpeg=True))
        # no ffmpeg: still rewrite to seekable m4a rather than an empty 200
        self.assertTrue(ms._stream_rewrite_to_audio("bytes=0-", {"fmt": "mp3"}, have_ffmpeg=False))


class HeadCacheRejectsNonMedia(unittest.TestCase):
    def test_put_skips_html(self):
        # _headc_put must refuse to store an error body under an audio ctype
        ok = ms._headc_put("aaaaaaaaaaa", "std", HTML, 4000, "audio/mp4", itag="140")
        self.assertFalse(ok)


class ClientLadderTest(unittest.TestCase):
    def test_player_fallback_changes_format_and_refreshes(self):
        html = (ROOT / "player.html").read_text(encoding="utf-8")
        self.assertIn("const APP_BUILD='ms-v113'", html)
        self.assertIn("_msA10=/Android 10/i.test(navigator.userAgent||'')", html)
        # first fallback always re-extracts standard m4a/aac
        self.assertIn("swap(`/audio?k=${K}&id=${r.id}&q=std&fresh=1`)", html)
        # later steps force a real format change (opus or mp3)
        self.assertIn("`/audio?k=${K}&id=${r.id}&q=hi&fresh=1`", html)
        self.assertIn("`/stream?k=${K}&id=${r.id}&fmt=mp3`", html)
        # Android 10 prefers mp3 before opus
        self.assertIn(
            "swap(_msA10?`/stream?k=${K}&id=${r.id}&fmt=mp3`:`/audio?k=${K}&id=${r.id}&q=hi&fresh=1`)",
            html,
        )
        # the v112 no-op ladder must be gone
        self.assertNotIn("swap(`/audio?k=${K}&id=${r.id}&q=std`)", html)
        self.assertNotIn("swap(`/stream?k=${K}&id=${r.id}`)", html)
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("const V='ms-v113'", sw)



class FfSourceTest(unittest.TestCase):
    def test_prefers_complete_local_blob(self):
        import shutil, tempfile
        td = Path(tempfile.mkdtemp(prefix="ms-ffsrc-"))
        old = ms.CACHE
        try:
            ms.CACHE = td
            vid = "bbbbbbbbbbb"
            binp = td / f"{vid}_std.bin"
            binp.write_bytes(FTYP + b"\x00" * (70 * 1024))
            self.assertEqual(ms._ff_source(vid), str(binp))
        finally:
            ms.CACHE = old
            shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
