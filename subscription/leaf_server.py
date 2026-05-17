#!/usr/bin/env python3
"""Reality residential subscription leaf server.

Serves a per-token subscription endpoint with three responsibilities:

1.  Hand back the rendered Clash / sing-box / v2rayN profile file under
    ``/<TOKEN>/<filename>`` (or ``/<TOKEN>/`` for the default profile).
2.  Read the kernel network-interface counters to track traffic on a
    per-month basis and emit a ``Subscription-Userinfo`` response header so
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
from datetime import datetime
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
PROFILE_TITLE = os.environ.get("PROFILE_TITLE", "Reality-Residential")
UPDATE_INTERVAL_HOURS = os.environ.get("UPDATE_INTERVAL_HOURS", "24")
FILE_DIR = Path(os.environ.get("FILE_DIR", "/etc/reality-resi-stack/files"))
DEFAULT_TARGET = os.environ.get("DEFAULT_TARGET", "profile.yaml")

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


def current_month_key() -> str:
    return datetime.now().strftime("%Y-%m")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def update_usage_state() -> int:
    """Maintain a monotonically increasing monthly counter despite reboots.

    If the kernel stats are unavailable this round, return the last persisted
    value without modifying state — the next round will try again.
    """
    current_total = read_total_bytes()
    if current_total is None:
        state = load_state()
        return int(state.get("used_bytes", 0)) if state else 0

    current_boot = read_boot_id()
    month_key = current_month_key()

    with state_lock:
        state = load_state()
        if not state:
            state = {
                "boot_id": current_boot,
                "last_total": current_total,
                "month": month_key,
                "used_bytes": current_total,
            }
            save_state(state)
            return int(state["used_bytes"])

        if state.get("month") != month_key:
            state = {
                "boot_id": current_boot,
                "last_total": current_total,
                "month": month_key,
                "used_bytes": 0,
            }
            save_state(state)
            return 0

        last_total = int(state.get("last_total", 0))
        used_bytes = int(state.get("used_bytes", 0))
        last_boot = state.get("boot_id", "")

        # Same boot, counter has not wrapped → add the delta.
        if current_boot == last_boot and current_total >= last_total:
            used_bytes += current_total - last_total

        state["boot_id"] = current_boot
        state["last_total"] = current_total
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
                "counter_used_bytes": used_bytes,
                "expire_ts": EXPIRE_TS,
                "interface": INTERFACE,
                "month": current_month_key(),
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
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), SubscriptionHandler)
    print(f"listening on {HOST}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
