# Built on the Scrapling image: Scrapling 0.5.1, mcp, markdownify, patchright + Chromium and its libs.
FROM pyd4vinci/scrapling:0.5.1

# Browsers live in /root/.cache/ms-playwright (world-readable). Opening /root (directory only, no file
# copies) lets an unprivileged user launch them.
RUN chmod 755 /root \
 && useradd --uid 10001 --create-home --shell /usr/sbin/nologin leanweb \
 && mkdir -p /data/cache && chown leanweb /data/cache

ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/srv/leanweb/src \
    LEANWEB_HOST=0.0.0.0 \
    LEANWEB_PORT=8200 \
    LEANWEB_CACHE_DIR=/data/cache

COPY src /srv/leanweb/src
USER leanweb
WORKDIR /srv/leanweb
VOLUME /data/cache
EXPOSE 8200
ENTRYPOINT ["/app/.venv/bin/python", "-m", "leanweb"]
