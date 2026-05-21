# Subscription server design

## Why ship our own subscription server

VLESS+Reality on its own only needs sing-box running on the server — the **subscription server** is an additional layer that publishes the client-side profile (`vless://` link, Clash YAML, sing-box JSON, ...) as HTTP endpoints. Worth writing rather than using an off-the-shelf panel because:

1. **Clients get "sync subscription" / "update subscription"**: when you later change the node (new IP, new SNI, add a node), clients pick it up on the next refresh — no manual edits on each device.
2. **Usage cards**: via the `Subscription-Userinfo` response header (v2rayN-community convention), clients render "X used / Y total / expires Z". That requires the server to actually know how much has been used.
3. **Health checks**: `/healthz` lets uptime monitoring probe directly.
4. **Aggregation / HA**: in dual-node setups, the aggregator polls the leaf's `/status` and serves a unified subscription YAML — clients subscribe to a single URL.

Existing tools (3x-ui, Sub-Hub, Sub-Store) either pull in a full admin panel or rely on external workers / Redis. The implementation here is **240 lines of standard-library-only Python** — auditable and dependency-free.

---

## Two servers, two roles

| Server | File | Where it runs |
|---|---|---|
| **Leaf** | `subscription/leaf_server.py` | On every host running sing-box. Reads `/sys/class/net/<iface>/statistics/*_bytes`, accumulates monthly traffic, and emits `Subscription-Userinfo`. |
| **Aggregator** | `subscription/aggregator_server.py` | On the data-center backup node in a dual-node setup. **Polls** the leaf's `/<TOKEN>/status` JSON, **caches** the result, and serves a unified Clash YAML listing both nodes. Falls back to the cache when the leaf is briefly unreachable. |

Single-node deployments run only the leaf. Dual-node deployments run both.

---

## Endpoint contract

Whether leaf or aggregator, the external contract is the same:

| Method | Path | Response |
|---|---|---|
| `GET`/`HEAD` | `/healthz` | `200 {"ok": true, "service": "<PROFILE_TITLE>"}` |
| `GET`/`HEAD` | `/<TOKEN>/` | Default subscription file (default `profile.yaml`), with usage-card headers |
| `GET`/`HEAD` | `/<TOKEN>/<filename>` | Named subscription file (leaf only; aggregator serves only the default) |
| `GET`/`HEAD` | `/<TOKEN>/status` | Machine-readable JSON usage summary |
| anything else | * | `404` |

**Key response headers:**

```http
Profile-Title: US-Resi-01
Profile-Update-Interval: 24
Content-Disposition: attachment; filename*=UTF-8''profile.yaml
Subscription-Userinfo: upload=0; download=10485760; total=1063004405760; expire=0
```

`Subscription-Userinfo` is a de-facto v2rayN-community standard; v2rayN, Clash Verge, Stash, Shadowrocket, and most maintained clients parse it.

---

## Configuration (environment)

Full reference in `templates/env/subscription-leaf.env.example` and `subscription-aggregator.env.example`. Highlights:

**Leaf:**

| Variable | Required | Purpose |
|---|---|---|
| `TOKEN` | ✓ | URL path prefix; the server only answers requests under `/<TOKEN>/` |
| `INTERFACE` | ✓ | NIC name, used to read `rx_bytes` / `tx_bytes` |
| `FILE_DIR` | | Directory of profile files (default `/etc/reality-resi-stack/files`) |
| `STATE_FILE` | | Persistent monthly counter |
| `USAGE_OFFSET_BYTES` | | Calibration baseline (use this when the counter starts mid-month) |
| `TOTAL_BYTES` | | Plan quota (display only) |
| `EXPIRE_TS` | | Plan expiry Unix timestamp; `0` hides it |

**Aggregator:**

| Variable | Required | Purpose |
|---|---|---|
| `TOKEN` | ✓ | Independent of the leaf's token |
| `REMOTE_STATUS_URL` | ✓ | The leaf's `/status` URL, fetched on every poll |
| `CACHE_FILE` | | Last-known-good remote status |
| `CACHE_TTL_SECONDS` | | Cache freshness window (default 60) |
| `FALLBACK_USED_BYTES` | | Fallback when neither cache nor leaf is available |

---

## Semantics of the traffic counter

**The leaf counts the host's monthly NIC RX+TX:**

```
read /sys/class/net/<INTERFACE>/statistics/rx_bytes
read /sys/class/net/<INTERFACE>/statistics/tx_bytes
accumulate by month, reset on month change
first sample establishes a baseline instead of counting pre-install host traffic
detect reboots via boot_id — add the new boot's current counter into monthly usage
add USAGE_OFFSET_BYTES before returning to clients (manual calibration)
```

The honest bounds of this:

✅ Accurate enough for client-side "how much do I have left this month" reminders.
✅ Within an order of magnitude of "how much did I burn this month."
❌ **Not the same as your VPS provider's billing**. Providers may bill on 95th-percentile, on outbound only, on 5-minute peaks — entirely different units.
❌ If the host runs other workloads (a personal web server, backups), that non-proxy traffic is included too.

When the provider dashboard is much higher than the subscription card, the usual cause is "the subscription server started later than the month did." The first sample is also intentionally treated as a baseline so pre-install host traffic is not dumped into the card. Apply a `USAGE_OFFSET_BYTES` to catch up (see [TROUBLESHOOTING.md](TROUBLESHOOTING.md), "Traffic counter drifts" section).

---

## Aggregator's cache-fallback logic

`current_usage()` resolution order:

1. **Cache fresh (< `CACHE_TTL_SECONDS`)** → use cache, do not bother the leaf
2. **Cache stale or missing** → pull from leaf, refresh cache
3. **Leaf unreachable** → use the last cached value (even if stale)
4. **No cache either** → fall back to `FALLBACK_USED_BYTES`

Why: clients refresh on `Profile-Update-Interval` (default 24 h). If the leaf is mid-restart at that moment, **returning 0 would yank the client's usage card back to zero** until the next refresh — a jarring visual jump that confuses users far more than "the number is slightly stale."

The fallback exists so the client card is **monotonic and never regresses**; admitting "slightly old data" is friendlier than admitting "data is missing."

---

## Running locally / debugging

The services are systemd-managed:

```bash
systemctl status subscription-leaf            # single-node
systemctl status subscription-aggregator      # the aggregator on the DC node
journalctl -u subscription-leaf -n 50 --no-pager
```

Run locally without systemd (for development):

```bash
cd /opt/reality-resi-stack/subscription
export TOKEN=test FILE_DIR=$(mktemp -d) INTERFACE=lo
echo 'foo: bar' > "$FILE_DIR/profile.yaml"
python3 leaf_server.py
# another terminal:
curl -i http://127.0.0.1:80/healthz
curl -I http://127.0.0.1:80/test/
```

---

## Next

- Deploy aggregator → [DUAL-NODE.md](DUAL-NODE.md)
- Usage card missing / counter wrong → [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
