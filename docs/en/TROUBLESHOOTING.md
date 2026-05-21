# Troubleshooting

Ordered by "symptom → most-common cause → fix." Always start with these baseline checks:

```bash
systemctl status sing-box --no-pager
journalctl -u sing-box -n 50 --no-pager
ss -tlnp | grep ':443'
ufw status verbose
sing-box check -C /etc/sing-box/conf
```

Issue templates will ask for the output of these first.

---

## Client cannot connect

| Likely cause | How to check |
|---|---|
| Cloud provider security group not allowing `443/tcp` | Check the provider console |
| UFW not allowing `443/tcp` | `ufw status` |
| Client UUID mismatch | Compare client `vless://` UUID vs server `secrets.env` |
| Client `public-key` wrong | Compare client `pbk=` vs server `REALITY_PUBLIC_KEY` |
| Client `servername` ≠ server `server_name` | Both must be the same SNI (e.g. `addons.mozilla.org`) |
| Client lacks Reality / `xtls-rprx-vision` support | Update to latest v2rayN / Clash Verge / sing-box |
| nginx/caddy/apache already holds 443 | `ss -tlnp \| grep 443` to see |
| sing-box config has an error | `sing-box check -C /etc/sing-box/conf` |

---

## Telegram / Discord uploads stalling, voice choppy

This is the **canonical "residential-IP soft-throttle" symptom**, and **not** a protocol problem.

**Diagnose:**
- Speed tests pass
- Text messages fine
- Large files, voice, and video uploads visibly degraded
- The same account works fine on a non-proxied connection

**Root cause:** your residential /24 has bot history; Telegram/Discord anti-abuse downranks the whole subnet regardless of your specific account.

**Fix:** dual-node + smart routing (route Telegram/Discord through a data-center node). See [DUAL-NODE.md](DUAL-NODE.md).

**Quick mitigation** without touching the server: add a Clash routing rule that diverts TG/Discord through any non-residential proxy you have available:

```yaml
rules:
  - DOMAIN-SUFFIX,telegram.org,your-backup-proxy
  - DOMAIN-SUFFIX,t.me,your-backup-proxy
  - DOMAIN-SUFFIX,discord.com,your-backup-proxy
  - IP-CIDR,91.108.4.0/22,your-backup-proxy,no-resolve
  - IP-CIDR,91.108.16.0/22,your-backup-proxy,no-resolve
  - IP-CIDR,149.154.160.0/20,your-backup-proxy,no-resolve
  # everything else through your default
```

---

## Subscription URL works but no usage card in the client

```bash
curl -I http://your-server-ip/your-token
```

You should see:

- `Subscription-Userinfo`
- `Profile-Title`
- `Profile-Update-Interval`

If all are present but the client doesn't render → the **client doesn't support** the card (older v2rayN, some mobile Clash forks). Switch clients; this does not affect proxying.

If headers are missing → check the leaf logs:

```bash
journalctl -u subscription-leaf -n 50 --no-pager
```

---

## Counter doesn't match provider dashboard

**Short answer:** expected behavior, not a bug.

**Long answer:** the subscription server counts `/sys/class/net/<iface>/statistics/rx_bytes + tx_bytes` monthly delta. Providers may bill on:

- Outbound only (your `tx_bytes`, not `rx + tx`)
- 95th-percentile (not accumulation)
- 5-minute peaks
- Adding control-plane traffic (DHCP / ARP / your own SSH session bytes)
- A "month" starting at a different timestamp than yours

**Calibrate** (align the card to match the dashboard from this moment on):

```bash
CURRENT_TOTAL=$(( $(cat /sys/class/net/eth0/statistics/rx_bytes) + $(cat /sys/class/net/eth0/statistics/tx_bytes) ))
STATE_USED=$(python3 -c "import json; print(int(json.load(open('/var/lib/reality-resi-stack/usage-state.json'))['used_bytes']))")
BACKEND_USED=900000000000   # bytes used per your provider's dashboard

OFFSET=$((BACKEND_USED - STATE_USED))
sudo sed -i "s/^USAGE_OFFSET_BYTES=.*/USAGE_OFFSET_BYTES=${OFFSET}/" /etc/reality-resi-stack/subscription-leaf.env
sudo systemctl restart subscription-leaf
```

If `usage-state.json` does not exist yet or was cleared during restore, hit `http://127.0.0.1/<TOKEN>/status` once to establish the baseline, then apply the formula above. `USAGE_OFFSET_BYTES` may be negative; the server clamps the final reported value to zero or above.

---

## TLS self-handshake fails / Reality doesn't seem to work

```bash
echo | openssl s_client -connect 127.0.0.1:443 -servername addons.mozilla.org 2>/dev/null | grep subject=
```

Should return the certificate subject of `addons.mozilla.org`. If it returns something else (sing-box self-signed, `cannot connect`):

- **sing-box not installed / not running**: `systemctl status sing-box`
- **SNI misconfigured**: `/etc/sing-box/conf/11_xtls-reality_inbounds.json` must have identical `tls.server_name` and `reality.handshake.server`
- **Server can't reach the SNI host**: try `curl -v https://addons.mozilla.org/` directly from the VPS
- **Reality private/public keys mismatched**: regenerate with `sing-box generate reality-keypair`, update both server and client

---

## fail2ban locked me out

```bash
fail2ban-client status sshd                   # see banned IPs
fail2ban-client set sshd unbanip 1.2.3.4      # unban
```

Prevention: always keep a parallel SSH session before applying `--harden-ssh`. Default jail: 5 failures → 1 h ban.

---

## sing-box service fails after upgrade

```bash
journalctl -u sing-box -n 100 --no-pager
sing-box check -C /etc/sing-box/conf
```

Most often a schema change in the new sing-box version. Cross-reference the [sing-box release notes](https://github.com/SagerNet/sing-box/releases). Short-term:

```bash
apt-get install -y sing-box=<last-known-good-version>
apt-mark hold sing-box   # pin
```

Then open an issue on this repo so we can ship the schema fix.

---

## NTP time sync fails

```bash
timedatectl
chronyc sources -v
```

Multiple sources with `Reach=0` usually means the provider blocks outbound `123/UDP`. **Does not block proxying** (VLESS doesn't depend on tight clock sync), but skews log timestamps. Switch to NTS:

```bash
sudo sed -i 's|^pool .*|pool time.cloudflare.com iburst nts|' /etc/chrony/chrony.conf
sudo systemctl restart chrony
```

---

## Broken config / want to roll back

```bash
ls /var/backups/reality-resi-stack/
tar -tzf /var/backups/reality-resi-stack/reality-resi-stack-2026-05-17-120000.tar.gz | head
```

Restore (stop services first):

```bash
systemctl stop sing-box
tar -xzf /var/backups/reality-resi-stack/reality-resi-stack-XXXX.tar.gz -C /
systemctl daemon-reload
systemctl start sing-box
sing-box check -C /etc/sing-box/conf
```

⚠️ Backups **do not** include `/var/lib/reality-resi-stack/usage-state.json` or `usage-cache.json` (runtime state), so after a restore the counter restarts. Archives include `/etc/reality-resi-stack/`, which contains secrets and tokens; do not share them publicly. Apply a `USAGE_OFFSET_BYTES` after restore (see "Counter doesn't match provider dashboard" above).

---

## Exit IP is not the expected residential IP

```bash
curl --proxy socks5h://127.0.0.1:7891 https://ipinfo.io
```

If the IP returned isn't your residential IP:

- Client rules may have routed the request elsewhere — check the rule match log in the client
- DNS contamination: client may have resolved direct without sniffing — check Clash's `mode: rule` and `dns:` section
- Your residential node may be down and the client fell back to a backup — `systemctl status sing-box` on the residential node

---

## Still stuck?

When filing an issue, please include:

- `journalctl -u sing-box -n 100 --no-pager`
- `sing-box version`
- `cat /etc/os-release | head -3`
- expected vs actual behavior
- **Do NOT** paste UUIDs, Reality keys, or server IPs

The issue template reminds you again.
