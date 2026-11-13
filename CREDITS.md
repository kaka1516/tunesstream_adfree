# Credits

## Instant-start head cache (2026-11-13)

Music Stream already resolved and cached googlevideo stream URLs (`lcache/urls`) and fetched media with bounded `Range` requests. The intro cache in `ms_headcache.py` adds a shared on-disk store of the first ~10–15 seconds (`Range: bytes=0-N`) so a later tap can send a `206` from disk immediately and only then pull the rest from upstream.

This follows a widely used pattern rather than copying any one project:

- **yt-dlp** (Unlicense) — the Rust client’s partial/probe pipeline requests `bytes=0-…` to obtain the start of a stream and the total size from `Content-Range`, then fetches later ranges as needed (`yt_dlp/client/streams/pipeline/partial.rs`).
- **Invidious / Piped** (AGPL) — the videoplayback proxies honor Range queries so a player can start before the whole file is fetched. The *idea* is reused; none of their source is included here.
- **nginx slice / [KinoBD/cloudflare-range-cache](https://github.com/KinoBD/cloudflare-range-cache)** (check that repo’s license) — cache aligned byte ranges and reassemble a correct `206`. We cache only the intro (plus our existing 1 MiB chunked blob cache) with an LRU cap.

If a cached intro cannot be read, playback always falls back to the upstream Range fetch.
