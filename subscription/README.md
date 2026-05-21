# subscription/

Two zero-dependency Python HTTP servers that turn the sing-box install into
a proper subscription endpoint with usage cards.

## Why two servers

| Server | Role | Where it runs |
|---|---|---|
| `leaf_server.py` | Reads `/sys/class/net/<iface>/statistics/*_bytes` on the host where sing-box lives, exposes the rendered Clash/sing-box profile, and emits `Subscription-Userinfo` headers. | On every node — at minimum, the residential node. |
| `aggregator_server.py` | Polls the leaf's `/<TOKEN>/status` JSON, caches it, and serves a *unified* dual-node profile. Falls back to the cache if the leaf is unreachable. | On the data-center backup node when you run a dual-node deployment. |

Both have **no third-party Python dependencies**. Standard library only. They
are designed to run as `systemd` services managed by `install/lib/subscription.sh`.

## Endpoint contract

| Method | Path | Response |
|---|---|---|
| `GET`/`HEAD` | `/healthz` | `200 {"ok": true, "service": "<PROFILE_TITLE>"}` |
| `GET`/`HEAD` | `/<TOKEN>/` | Default profile file, with `Subscription-Userinfo` etc. |
| `GET`/`HEAD` | `/<TOKEN>/<filename>` | Named profile file (leaf only — aggregator only serves the default). |
| `GET`/`HEAD` | `/<TOKEN>/status` | Machine-readable JSON usage summary. |
| `GET` any other path | `404 Not Found`. |

The `Subscription-Userinfo` header follows the original
[`v2rayN` convention](https://github.com/2dust/v2rayN/wiki/%E5%88%86%E7%89%87%E8%A7%84%E5%88%99):
`upload=0; download=<bytes>; total=<bytes>; expire=<unix-ts-or-0>`.

## State files

| File | Owner | Purpose |
|---|---|---|
| `/var/lib/reality-resi-stack/usage-state.json` | leaf | Monotonically increasing monthly counter; first sample is a baseline and the counter rolls over on month change. |
| `/var/lib/reality-resi-stack/usage-cache.json` | aggregator | Last-known-good remote status; serves as fallback when the leaf is down. |

State files are excluded from backups intentionally — they are runtime data,
not configuration.

Config backups do include `/etc/reality-resi-stack/`, which may contain
tokens and generated Reality credentials. Treat backup archives as sensitive.

## Running locally (test)

```bash
export TOKEN=test-token
export FILE_DIR=$(pwd)/test-files
export STATE_FILE=$(mktemp)
export INTERFACE=lo
mkdir -p "$FILE_DIR" && echo 'foo: bar' > "$FILE_DIR/profile.yaml"
python3 leaf_server.py
# then: curl -i http://127.0.0.1:80/healthz
```
