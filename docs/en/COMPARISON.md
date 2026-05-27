# Comparison

This is not a universal "best proxy project" ranking. It scores tools for one specific use case:

> You already own a VPS, especially a residential-IP VPS. You want a self-hosted VLESS Reality node, beginner-friendly deployment, low maintenance, and a practical answer to Telegram / Discord soft-throttling on some residential subnets.

If you need a multi-user commercial panel, billing, or expiry management, 3x-ui / x-ui may be a better fit. If you need a simple, auditable, low-exposure residential-IP node for yourself or a small team, `reality-resi-stack` is deliberately narrower.

## Overall score

Scores are 1-5. Higher means better fit for "residential-IP self-hosted VLESS Reality + beginner deployment + low maintenance".

| Option | Score | Best fit | Trade-off |
|---|---:|---|---|
| reality-resi-stack | 4.7 | Personal residential-IP users, small teams, AI-tool users | Narrow scope, fast deployment, strong residential-IP workflow, no multi-user panel |
| 3x-ui | 3.8 | Users who need a web panel, many protocols, and multi-user management | Rich features, higher operational surface |
| x-ui | 3.5 | Users who want an Xray panel for multi-protocol management | Strong panel workflow, residential-IP split routing is not the default focus |
| Manual Xray/sing-box config | 3.2 | Operators who already understand protocol details | Most flexible, highest beginner cost |
| Commercial proxy service | 2.8 | Users who do not want to run servers | Convenient, less auditable, residential egress is not under your control |

## Dimension scores

| Dimension | reality-resi-stack | 3x-ui | x-ui | Manual config | Commercial service |
|---|---:|---:|---:|---:|---:|
| Residential-IP fit | 5 | 3 | 3 | 4 | 2 |
| Beginner deployment | 5 | 4 | 4 | 1 | 5 |
| Subscription URL / usage card | 4 | 4 | 4 | 1 | 4 |
| Telegram / Discord split routing | 5 | 3 | 3 | 4 | 2 |
| Secure defaults | 4 | 3 | 3 | 2 | 2 |
| Auditability | 5 | 3 | 3 | 5 | 1 |
| Operational complexity | 4 | 3 | 3 | 2 | 5 |
| Multi-user / panel capability | 1 | 5 | 5 | 2 | 4 |

## Why reality-resi-stack is stronger for this use case

### 1. It treats the residential IP as the asset

Many generic installers and panels target the "cheap VPS proxy" use case: many protocols, many users, and panel management. `reality-resi-stack` starts from a different premise: residential egress reputation is valuable, so it should be used for OpenAI, Anthropic, Netflix, banking, and similar services.

### 2. Telegram / Discord slowdown is a first-class problem

Some residential IP ranges get soft-throttled by messaging platforms. Symptoms include Telegram uploads stuck on "sending" and poor Discord voice quality. Dual-node mode routes OpenAI / Claude through the residential node and Telegram / Discord through a data-center fallback while clients still import one subscription.

### 3. No exposed web panel by default

The strength of 3x-ui / x-ui is web-based management and multi-user control. That also adds a login surface, database state, panel upgrades, and access-control concerns. This project uses Bash + systemd + file templates by default, which is a better fit for single-user and small-team deployments.

### 4. It is repeatable

The installer supports `--dry-run`, `--config`, `--non-interactive`, and idempotent re-runs. You can inspect actions first, then apply them; you can also keep variables in a config file and reproduce the setup on another server.

### 5. It includes the boring operational basics

The stack handles systemd services, UFW / fail2ban, BBR, swap, journald limits, daily config backups, `/healthz`, and `Subscription-Userinfo`. These are not flashy features; they are the maintenance pieces beginners usually miss.

## When not to choose it

Do not use `reality-resi-stack` for every problem:

- You need many user accounts, limits, expiry dates, and admin controls: choose 3x-ui / x-ui.
- You need to manage inbounds, outbounds, and users every day through a Web UI: choose a panel.
- You want to learn every sing-box / Xray field: start from official docs and manual config.
- You do not want to maintain a server or use SSH: buy a commercial service.
- You need Kubernetes, Docker Compose, or an enterprise multi-tenant platform: out of scope.

## Sources and boundaries

The comparison uses public project descriptions and official docs:

- [3x-ui README](https://github.com/MHSanaei/3x-ui): web-based Xray-core control panel, multi-protocol support, multi-user management, traffic/expiry/IP limits, one-line install.
- [x-ui README](https://github.com/sing-web/x-ui): Xray panel, multi-protocol and multi-inbound/client management, traffic status, subscription and API features.
- [Project X docs](https://xtls.github.io/): VLESS, XTLS, REALITY, and routing are core Xray ecosystem capabilities.
- [sing-box route docs](https://sing-box.sagernet.org/configuration/route/): route rules can send traffic to different outbounds by domain, IP, port, protocol, and related matchers.

These sources are used only for capability boundaries and scenario comparison. Scores are product judgments for this repository's target user, not universal technical superiority claims.

## Next

- First deployment: [Beginner guide](BEGINNER_GUIDE.md)
- Already comfortable with SSH: [Deployment](DEPLOYMENT.md)
- Import clients: [Client import](CLIENTS.md)
- Telegram / Discord is slow: [Dual-node smart routing](DUAL-NODE.md)
