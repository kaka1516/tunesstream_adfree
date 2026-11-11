# Music Stream server image (ms-v75). Server only: the browser (phone/PC) does all audio decoding and visuals.
#   docker build -t music-stream .                       (with ffmpeg + node, ~250 MB)
#   docker build --build-arg WITH_FFMPEG=0 -t music-stream:lite .   (no mp3 transcode / fallback stream)
#   docker run -d -p 8121:8121 -v ms-data:/data music-stream        (key: docker exec <id> cat /data/music.env)
FROM python:3.12-alpine
ARG WITH_FFMPEG=1
ARG WITH_NODE=1
RUN apk add --no-cache ca-certificates \
 && if [ "$WITH_FFMPEG" = 1 ]; then apk add --no-cache ffmpeg; fi \
 && if [ "$WITH_NODE" = 1 ]; then apk add --no-cache nodejs; fi \
 && pip install --no-cache-dir "yt-dlp[default]" unidecode syncedlyrics
WORKDIR /app
COPY music_server.py famlang.py famkey.js famlang.js player.html sw.js game.js icon-192.png icon-512.png icon.svg favicon.ico ./
COPY assets ./assets
COPY vendor ./vendor
COPY skins ./skins
COPY scripts ./scripts
# ms-v77: fail the build if restricted (non-redistributable) assets slipped into the context
RUN sh scripts/check-restricted-assets.sh /app
# config + key live in the volume; the server creates MUSIC_KEY on first start
RUN mkdir -p /data && ln -sf /data/music.env /app/music.env
ENV MUSIC_PORT=8121 PYTHONUNBUFFERED=1
RUN printf 'MUSIC_BIND=0.0.0.0\nYTDLP_AUTO_UPDATE=0\n' > /tmp/env.defaults
EXPOSE 8121
CMD ["sh", "-c", "[ -s /data/music.env ] || cp /tmp/env.defaults /data/music.env; if command -v node >/dev/null; then grep -q ^YTDLP_JS_RUNTIME= /data/music.env || echo YTDLP_JS_RUNTIME=node >> /data/music.env; else grep -q ^YTDLP_JS_RUNTIME= /data/music.env || echo YTDLP_JS_RUNTIME=none >> /data/music.env; fi; exec python music_server.py"]
