#!/usr/bin/env python3
"""Reality residential subscription leaf server.

Serves a per-token subscription endpoint with three responsibilities:

1.  Hand back the rendered Clash / sing-box / v2rayN profile file under
    ``/<TOKEN>/<filename>`` (or ``/<TOKEN>/`` for the default profile).
2.  Read the kernel network-interface counters to track traffic on a
    per-billing-period basis and emit a ``Subscription-Userinfo`` response header so
    clients can render a usage card.
3.  Expose ``/healthz`` (liveness) and ``/<TOKEN>/status`` (machine-readable
    usage summary) for monitoring and for aggregator nodes to poll.

All configuration is via environment; see ``templates/env/subscription-leaf.env.example``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time as time_module
from datetime import datetime, time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("leaf")

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "80"))
TOKEN = os.environ["TOKEN"].strip("/")
INTERFACE = os.environ.get("INTERFACE", "eth0")
STATE_FILE = Path(os.environ.get(
    "STATE_FILE", "/var/lib/reality-resi-stack/usage-state.json"))
TOTAL_BYTES = int(os.environ.get("TOTAL_BYTES", "0"))
USAGE_OFFSET_BYTES = int(os.environ.get("USAGE_OFFSET_BYTES", "0"))
EXPIRE_TS = int(os.environ.get("EXPIRE_TS", "0"))
BILLING_CYCLE_DAY = int(os.environ.get("BILLING_CYCLE_DAY", "1"))
USAGE_POLL_INTERVAL_SECONDS = int(os.environ.get("USAGE_POLL_INTERVAL_SECONDS", "60"))
COUNT_CURRENT_BOOT_ON_INIT = os.environ.get("COUNT_CURRENT_BOOT_ON_INIT", "true").lower() in {
    "1",
    "true",
    "yes",
}
PROFILE_TITLE = os.environ.get("PROFILE_TITLE", "Reality-Residential")
UPDATE_INTERVAL_HOURS = os.environ.get("UPDATE_INTERVAL_HOURS", "24")
FILE_DIR = Path(os.environ.get("FILE_DIR", "/etc/reality-resi-stack/files"))
DEFAULT_TARGET = os.environ.get("DEFAULT_TARGET", "profile.yaml")
REQUEST_TIMEOUT_SECONDS = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "10"))

CONTENT_TYPES = {
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}

state_lock = threading.Lock()


def read_total_bytes() -> int | None:
    """Sum rx_bytes + tx_bytes for INTERFACE.

    Returns None (rather than crashing the request) if the kernel stats files
    are missing — this happens when INTERFACE was renamed, removed, or when
    running on a non-Linux host. The caller treats None as "skip accounting
    this round" so the server keeps serving the profile file.
    """
    base = Path("/sys/class/net") / INTERFACE / "statistics"
    try:
        with (base / "rx_bytes").open("r", encoding="utf-8") as h:
            rx = int(h.read().strip())
        with (base / "tx_bytes").open("r", encoding="utf-8") as h:
            tx = int(h.read().strip())
        return rx + tx
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        log.warning("read_total_bytes(%s) failed: %s — accounting skipped this round",
                    INTERFACE, exc)
        return None


def read_boot_id() -> str:
    try:
        return Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except (FileNotFoundError, PermissionError):
        return "unknown"


def current_period_key(now: datetime | None = None) -> str:
    """Return the accounting period key.

    BILLING_CYCLE_DAY=1 behaves like a calendar month. Other values anchor the
    period on the provider's billing reset day, e.g. day 11 yields
    ``2026-05-11`` for traffic between May 11 and June 10.
    """
    now = now or datetime.now()
    day = min(max(BILLING_CYCLE_DAY, 1), 28)
    year = now.year
    month = now.month
    if now.day < day:
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def next_billing_reset_ts(now: datetime | None = None) -> int:
    now = now or datetime.now()
    day = min(max(BILLING_CYCLE_DAY, 1), 28)
    year = now.year
    month = now.month
    if now.day >= day:
        month += 1
        if month == 13:
            month = 1
            year += 1
    reset_at = datetime.combine(datetime(year, month, day).date(), time.min)
    return int(reset_at.timestamp())


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("load_state(%s) failed: %s — reinitializing accounting state", STATE_FILE, exc)
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def update_usage_state() -> int:
    """Maintain a monotonically increasing billing-period counter despite reboots.

    If the kernel stats are unavailable this round, return the last persisted
    value without modifying state — the next round will try again.
    """
    current_total = read_total_bytes()
    if current_total is None:
        state = load_state()
        return int(state.get("used_bytes", 0)) if state else 0

    current_boot = read_boot_id()
    period_key = current_period_key()

    with state_lock:
        state = load_state()
        if not state:
            state = {
                "boot_id": current_boot,
                "last_total": current_total,
                "period": period_key,
                "used_bytes": current_total if COUNT_CURRENT_BOOT_ON_INIT else 0,
            }
            save_state(state)
            return int(state["used_bytes"])

        state_period = state.get("period", state.get("month"))
        if state_period != period_key:
            state = {
                "boot_id": current_boot,
                "last_total": current_total,
                "period": period_key,
                "used_bytes": 0,
            }
            save_state(state)
            return 0

        last_total = int(state.get("last_total", 0))
        used_bytes = int(state.get("used_bytes", 0))
        last_boot = state.get("boot_id", "")

        # Same boot, counter has not wrapped: add only the delta.
        if current_boot == last_boot and current_total >= last_total:
            used_bytes += current_total - last_total
        else:
            # Reboot, counter rollover, or restored state: kernel counters
            # restarted from a lower baseline, so count the current boot total.
            used_bytes += current_total

        state["boot_id"] = current_boot
        state["last_total"] = current_total
        state["period"] = period_key
        state.pop("month", None)
        state["used_bytes"] = used_bytes
        save_state(state)
        return used_bytes


def reported_used_bytes(used_bytes: int) -> int:
    return max(0, USAGE_OFFSET_BYTES + used_bytes)


def safe_target_path(target: str) -> Path | None:
    """Resolve ``target`` inside ``FILE_DIR`` while rejecting traversal."""
    target = target.strip("/")
    if not target:
        target = DEFAULT_TARGET
    # Reject anything with a path separator — only direct filenames allowed.
    if target != Path(target).name:
        return None
    return FILE_DIR / target


def content_type_for(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


class SubscriptionHandler(BaseHTTPRequestHandler):
    server_version = "RealityResiStack-Leaf/1.0"

    def do_GET(self) -> None:  # noqa: N802
        self.handle_request(send_body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        self.handle_request(send_body=False)

    def handle_request(self, send_body: bool) -> None:
        raw_path = unquote(self.path.split("?", 1)[0]).strip("/")
        if raw_path == "healthz":
            payload = json.dumps({"ok": True, "service": PROFILE_TITLE}).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(payload)
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
        used_bytes = update_usage_state()
        reported_bytes = reported_used_bytes(used_bytes)

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
            f"upload=0; download={reported_bytes}; total={TOTAL_BYTES}; expire={EXPIRE_TS}",
        )
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def serve_status(self, send_body: bool) -> None:
        used_bytes = update_usage_state()
        reported_bytes = reported_used_bytes(used_bytes)
        payload = json.dumps(
            {
                "billing_cycle_day": BILLING_CYCLE_DAY,
                "billing_reset_ts": next_billing_reset_ts(),
                "counter_used_bytes": used_bytes,
                "count_current_boot_on_init": COUNT_CURRENT_BOOT_ON_INIT,
                "expire_ts": EXPIRE_TS,
                "interface": INTERFACE,
                "period": current_period_key(),
                "poll_interval_seconds": USAGE_POLL_INTERVAL_SECONDS,
                "profile_title": PROFILE_TITLE,
                "reported_used_bytes": reported_bytes,
                "total_bytes": TOTAL_BYTES,
                "usage_offset_bytes": USAGE_OFFSET_BYTES,
                "used_bytes": used_bytes,
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
    start_usage_polling()
    server = TimeoutThreadingHTTPServer((HOST, PORT), SubscriptionHandler)
    log.info("listening on %s:%s", HOST, PORT)
    server.serve_forever()


def usage_poll_loop() -> None:
    while True:
        try:
            update_usage_state()
        except Exception as exc:  # noqa: BLE001
            log.warning("usage poll failed: %s", exc)
        time_module.sleep(max(5, USAGE_POLL_INTERVAL_SECONDS))


def start_usage_polling() -> None:
    thread = threading.Thread(target=usage_poll_loop, name="usage-poll", daemon=True)
    thread.start()


if __name__ == "__main__":
    main()
