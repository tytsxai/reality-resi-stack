# Client import

After install, the server prints either a `vless://` link or a subscription URL (if you used `--with-subscription`).

**Strongly prefer the subscription URL over pasting `vless://` into every client.** Once you change a node (new IP, new SNI, add a node), clients pick it up on the next refresh; with pasted `vless://` you would touch every device.

---

## Minimum supported client versions

| Client | Platform | Min version | Reality | xtls-rprx-vision | Usage card |
|---|---|---|---|---|---|
| v2rayN | Windows | 6.0+ | ✓ | ✓ | ✓ |
| Clash Verge / Verge Rev | Win/Mac/Linux | 1.4+ | ✓ | ✓ | ✓ |
| Stash | iOS/macOS | 2.5+ | ✓ | ✓ | ✓ |
| sing-box client | All | 1.7+ | ✓ | ✓ | partial |
| Hiddify | All | 2.0+ | ✓ | ✓ | ✓ |
| Streisand | iOS | 2024+ | ✓ | ✓ | ✓ |
| Shadowrocket | iOS | 2.2+ | ✓ | ✓ | ✓ |
| v2rayNG | Android | 1.8+ | ✓ | ✓ | ✓ |
| NekoBox | Android | 1.3+ | ✓ | ✓ | ✓ |

⚠️ Older Clash for Windows and ClashX do **not** support Reality. Switch to a Verge fork or Stash.

---

## Windows · v2rayN

1. Download latest [v2rayN](https://github.com/2dust/v2rayN/releases)
2. Open → `Subscriptions` → `Subscription settings` → `Add`
3. Fill in:
   - Remarks: `reality-resi-stack`
   - URL: your subscription URL (`http://your-server/your-token`)
4. OK → right-click a node → `Subscription` → `Update`
5. Select node → `Ctrl+T` to test latency
6. System proxy → `Set system proxy automatically`

---

## macOS · Clash Verge Rev

1. Download [Clash Verge Rev](https://github.com/clash-verge-rev/clash-verge-rev/releases)
2. Install and open → `Profiles` tab
3. Paste subscription URL → `Download`
4. Select the new profile → enable
5. Top bar → `Outbound Mode` → `Rule`
6. System proxy: menu bar icon → `System Proxy` on

---

## iOS · Stash (recommended, paid)

1. App Store: install Stash
2. Open → `Profiles` → top-right `+` → `URL` → paste subscription URL
3. Wait for download → select profile → enable
4. Home → drag the bottom switch to start the VPN

---

## iOS · Shadowrocket (paid, not available on CN App Store)

1. Copy the `vless://` link to clipboard
2. Open Shadowrocket → home → top-right `+` — it auto-detects the clipboard
3. Or: `Server` tab → top-right `+` → `Subscribe` → paste subscription URL

---

## Android · v2rayNG / NekoBox

1. Install the latest v2rayNG or NekoBox
2. Top-right `+` → `Import config from clipboard` (paste `vless://`)
   - Or: `Settings` → `Subscription settings` → add URL → update
3. Select node → big play button at the bottom

---

## sing-box mobile (Android / iOS)

The cleanest experience but slightly more hands-on.

1. Install sing-box from App Store / Play / GitHub Releases
2. `Configuration` → New → paste from `examples/single-node/sing-box-client-outbound.json` (replace placeholders with your real values)
3. Home → start

Subscription mode: sing-box client supports subscription URLs natively, but expects sing-box JSON, not Clash YAML. The repo's default subscription server emits Clash YAML, so sing-box client users typically use the manual-paste path above.

---

## Confirm the client is actually using your node

Visit [https://ipinfo.io](https://ipinfo.io) in a browser. You should see:

- IP = your VPS's public IP
- ASN tagged with your VPS's ISP
- Geolocation = your VPS's city

If you see your real local IP, the client isn't routing through the proxy. Check:

- System proxy / TUN mode is on in the client
- Browser is using the system proxy (macOS/Linux Firefox doesn't follow system proxy by default — set manually)
- Client rules haven't routed this domain to DIRECT

---

## Confirm OpenAI/ChatGPT works (the residential IP's value proposition)

```bash
curl -i https://api.openai.com/v1/models
```

Expect `HTTP/2 401` (no API key → 401, **which means OpenAI accepted your IP**). If you see `403 Country, region, or territory not supported`, OpenAI rejected your exit IP — usually means the IP is classified as non-residential or is on a blocklist.

---

## Client import for dual-node

After deploying dual-node, the subscription URL returns a Clash YAML that already contains **both nodes + smart routing rules**. The import flow is identical to single-node — **no additional configuration required**.

After import, the client shows:

- 2 nodes (e.g. `US-Resi-01` and `US-DC-01`)
- 3 proxy groups: `RESI`, `DC`, `AUTO`
- A pre-written ruleset (TG → DC, OpenAI → RESI, others → AUTO)

To override a specific rule, edit the client's "ruleset" directly — no need to touch the server.

---

## Things go wrong?

- Card doesn't show traffic → [TROUBLESHOOTING.md](TROUBLESHOOTING.md), "Subscription URL works but no usage card"
- Client can't connect → [TROUBLESHOOTING.md](TROUBLESHOOTING.md), "Client cannot connect"
- TG uploads slow → [DUAL-NODE.md](DUAL-NODE.md), or [TROUBLESHOOTING.md](TROUBLESHOOTING.md), "Telegram / Discord"
