#!/usr/bin/env python3
"""Reality residential subscription aggregator server.

Lives on the data-center backup node (or anywhere with a stable public IP)
and serves a unified Clash profile listing both the residential leaf and the
data-center node. The profile typically routes Telegram / Discord through
this DC node (which has cleaner messenger reputation) and routes OpenAI /
Anthropic / Netflix through the residential leaf (which earns "real home
user" reputation with those services).

For traffic accounting, this server polls the leaf's ``/status`` endpoint,
caches the result, and falls back to the cached value if the leaf becomes
unreachable — avoiding the "0 bytes used" jitter that would otherwise
confuse the client's usage card.

All configuration is via environment; see
``templates/env/subscription-aggregator.env.example``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote
from urllib.request import Request, urlopen

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("aggregator")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "80"))
TOKEN = os.environ["TOKEN"].strip("/")
FILE_DIR = Path(os.environ.get("FILE_DIR", "/etc/reality-resi-stack/files"))
DEFAULT_TARGET = os.environ.get("DEFAULT_TARGET", "profile.yaml")
CACHE_FILE = Path(os.environ.get(
    "CACHE_FILE", "/var/lib/reality-resi-stack/usage-cache.json"))
CACHE_TTL_SECONDS = float(os.environ.get("CACHE_TTL_SECONDS", "60"))
REMOTE_POLL_INTERVAL_SECONDS = float(
    os.environ.get("REMOTE_POLL_INTERVAL_SECONDS", CACHE_TTL_SECONDS)
)
TOTAL_BYTES = int(os.environ.get("TOTAL_BYTES", "0"))
FALLBACK_USED_BYTES = int(os.environ.get("FALLBACK_USED_BYTES", "0"))
EXPIRE_TS = int(os.environ.get("EXPIRE_TS", "0"))
PROFILE_TITLE = os.environ.get("PROFILE_TITLE", "Reality-Residential-Dual")
UPDATE_INTERVAL_HOURS = os.environ.get("UPDATE_INTERVAL_HOURS", "24")
REMOTE_STATUS_URL = os.environ.get("REMOTE_STATUS_URL", "")
REMOTE_TIMEOUT_SECONDS = float(os.environ.get("REMOTE_TIMEOUT_SECONDS", "3"))
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10"))

CONTENT_TYPES = {
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def read_remote_status() -> dict:
    if not REMOTE_STATUS_URL:
        return {}
    request = Request(REMOTE_STATUS_URL, headers={"User-Agent": "RealityResiStack-Aggregator/1.0"})
    with urlopen(request, timeout=REMOTE_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def save_usage_cache(used_bytes: int, status: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reported_used_bytes": used_bytes,
        "remote_status": status,
        "cached_at": int(time.time()),
    }
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def read_usage_cache() -> tuple[int, dict] | None:
    if not CACHE_FILE.is_file():
        return None
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        used_bytes = int(payload.get("reported_used_bytes", FALLBACK_USED_BYTES))
        return max(0, used_bytes), payload
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def current_usage() -> tuple[int, dict]:
    """Return (bytes_used, metadata).

    Resolution order: fresh cache → live poll → stale cache → fallback.
    """
    cached = read_usage_cache()

    # If cache is still fresh, use it without hitting the network.
    if cached is not None:
        cached_used, cached_payload = cached
        age = time.time() - int(cached_payload.get("cached_at", 0))
        if age < CACHE_TTL_SECONDS:
            return cached_used, {"source": "cache-fresh", "age": age, "cache": cached_payload}

    # Cache miss or stale → refresh from leaf.
    try:
        status = read_remote_status()
        reported = int(status.get("reported_used_bytes",
                                  status.get("used_bytes", FALLBACK_USED_BYTES)))
        reported = max(0, reported)
        save_usage_cache(reported, status)
        return reported, {"source": "remote_status", "remote_status": status}
    except Exception as exc:  # noqa: BLE001
        if cached is not None:
            cached_used, cached_payload = cached
            return cached_used, {
                "source": "cache-stale-fallback",
                "error": str(exc),
                "cache": cached_payload,
            }
        return max(0, FALLBACK_USED_BYTES), {"source": "fallback", "error": str(exc)}


def refresh_usage_cache() -> tuple[int, dict]:
    """Poll the leaf and refresh cache, ignoring cache freshness."""
    try:
        status = read_remote_status()
        reported = int(status.get("reported_used_bytes",
                                  status.get("used_bytes", FALLBACK_USED_BYTES)))
        reported = max(0, reported)
        save_usage_cache(reported, status)
        return reported, {"source": "remote_status", "remote_status": status}
    except Exception as exc:  # noqa: BLE001
        cached = read_usage_cache()
        if cached is not None:
            cached_used, cached_payload = cached
            return cached_used, {
                "source": "cache-stale-fallback",
                "error": str(exc),
                "cache": cached_payload,
            }
        return max(0, FALLBACK_USED_BYTES), {"source": "fallback", "error": str(exc)}


def safe_target_path(target: str) -> Path | None:
    target = target.strip("/")
    if not target:
        target = DEFAULT_TARGET
    if target != Path(target).name:
        return None
    return FILE_DIR / target


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class AggregatorHandler(BaseHTTPRequestHandler):
    server_version = "RealityResiStack-Aggregator/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self.handle_request(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self.handle_request(send_body=False)

    def handle_request(self, send_body: bool) -> None:
        raw_path = unquote(self.path.split("?", 1)[0]).strip("/")
        if raw_path == "healthz":
            self.serve_health(send_body)
            return

        parts = raw_path.split("/", 1) if raw_path else []
        if not parts or parts[0] != TOKEN:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        target = DEFAULT_TARGET if len(parts) == 1 or not parts[1] else parts[1]
        if target == "status":
            self.serve_status(send_body)
            return

        file_path = safe_target_path(target)
        if file_path is None or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        body = file_path.read_bytes()
        used_bytes, _meta = current_usage()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type_for(file_path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Profile-Title", PROFILE_TITLE)
        self.send_header("Profile-Update-Interval", UPDATE_INTERVAL_HOURS)
        self.send_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{file_path.name}",
        )
        self.send_header(
            "Subscription-Userinfo",
            f"upload=0; download={used_bytes}; total={TOTAL_BYTES}; expire={EXPIRE_TS}",
        )
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def serve_health(self, send_body: bool) -> None:
        payload = json.dumps(
            {"ok": True, "service": PROFILE_TITLE},
            ensure_ascii=True,
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def serve_status(self, send_body: bool) -> None:
        used_bytes, meta = current_usage()
        payload = json.dumps(
            {
                "expire_ts": EXPIRE_TS,
                "poll_interval_seconds": REMOTE_POLL_INTERVAL_SECONDS,
                "profile_title": PROFILE_TITLE,
                "reported_used_bytes": used_bytes,
                "total_bytes": TOTAL_BYTES,
                **meta,
            },
            ensure_ascii=True,
        ).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        log.info("%s - %s", self.address_string(), fmt % args)


class TimeoutThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def get_request(self):  # type: ignore[no-untyped-def]
        sock, addr = super().get_request()
        sock.settimeout(REQUEST_TIMEOUT_SECONDS)
        return sock, addr


def main() -> None:
    start_remote_polling()
    server = TimeoutThreadingHTTPServer((HOST, PORT), AggregatorHandler)
    log.info("listening on %s:%s", HOST, PORT)
    server.serve_forever()


def remote_poll_loop() -> None:
    while True:
        _used_bytes, meta = refresh_usage_cache()
        if meta.get("source") != "remote_status":
            log.warning(
                "remote status poll used %s: %s",
                meta.get("source"),
                meta.get("error", "no error detail"),
            )
        time.sleep(max(5, REMOTE_POLL_INTERVAL_SECONDS))


def start_remote_polling() -> None:
    thread = threading.Thread(target=remote_poll_loop, name="remote-status-poll", daemon=True)
    thread.start()


if __name__ == "__main__":
    main()
