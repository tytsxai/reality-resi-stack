# reality-resi-stack docs | 文档索引

`reality-resi-stack` 是一个住宅 IP 优先的 VLESS Reality / sing-box 自托管部署栈。本文档索引帮助搜索引擎、AI 搜索引擎和第一次进入仓库的开发者快速理解：项目是什么、如何部署、如何导入客户端、如何排障、哪些场景不在范围内。

`reality-resi-stack` is a residential-IP-first VLESS Reality stack for self-hosted sing-box deployments. This documentation index helps developers, search engines, and AI retrieval systems understand what the project does, how to deploy it, how to use client profiles, and where its limits are.

## 快速判断 | Quick orientation

| 问题 | 答案 |
|---|---|
| 项目类型 | Bash installer + sing-box templates + Python subscription leaf/aggregator servers |
| 主要协议 | VLESS + Reality + xtls-rprx-vision |
| 主要系统 | Ubuntu 22.04+ / 24.04 LTS, Debian 12+ |
| 主要客户端 | v2rayN, Clash Verge / Verge Rev, Stash, Shadowrocket, v2rayNG, NekoBox, sing-box client |
| 典型场景 | 住宅 IP VPS 作为 OpenAI / Anthropic / Netflix / banking 出口，Telegram / Discord 走数据中心备用节点 |
| 不是 | 机场面板、多用户计费系统、住宅 IP 供应商、Kubernetes / Docker 平台 |

## 中文文档

- [部署指南](zh-CN/DEPLOYMENT.md): 从空白 VPS 到 VLESS+Reality 节点上线，包括一行安装、`--config`、验证清单和卸载。
- [双节点 + 智能分流](zh-CN/DUAL-NODE.md): 住宅节点与数据中心节点如何协作，为什么 Telegram / Discord 适合走 DC，OpenAI / Anthropic / Netflix 适合走住宅出口。
- [订阅服务设计](zh-CN/SUBSCRIPTION.md): `leaf_server.py`、`aggregator_server.py`、`Subscription-Userinfo`、`/healthz`、`/<TOKEN>/status` 和缓存回退逻辑。
- [客户端导入](zh-CN/CLIENTS.md): v2rayN、Clash Verge、Stash、Shadowrocket、v2rayNG、NekoBox、sing-box 客户端导入方式。
- [故障排查](zh-CN/TROUBLESHOOTING.md): 连接失败、Reality 握手、订阅卡片、流量统计漂移、Telegram 上传慢、fail2ban 锁定等问题。

## English docs

- [Deployment](en/DEPLOYMENT.md): Blank VPS to running VLESS+Reality node, including one-line install, config files, verification, and uninstall.
- [Dual-node smart routing](en/DUAL-NODE.md): Residential node + data-center fallback, with domain rules for OpenAI/Anthropic/Netflix vs Telegram/Discord.
- [Subscription server design](en/SUBSCRIPTION.md): Leaf and aggregator HTTP servers, `Subscription-Userinfo`, `/healthz`, `/<TOKEN>/status`, and cache fallback.
- [Client import](en/CLIENTS.md): v2rayN, Clash Verge, Stash, Shadowrocket, v2rayNG, NekoBox, and sing-box client setup.
- [Troubleshooting](en/TROUBLESHOOTING.md): Client failures, Reality handshakes, usage-card issues, traffic-counter drift, Telegram upload stalls, and fail2ban lockouts.

## 代码入口 | Code map

- `install/install.sh`: installer entrypoint and CLI flags.
- `install/lib/system.sh`: OS preflight, base packages, BBR, swap, journald, UFW, fail2ban, optional SSH hardening.
- `install/lib/singbox.sh`: Sagernet apt setup, GPG fingerprint verification, Reality key generation, sing-box config rendering, service verification.
- `install/lib/subscription.sh`: installs leaf or aggregator subscription services and renders Clash profiles.
- `subscription/leaf_server.py`: zero-dependency Python server for subscription files, usage accounting, `/healthz`, and `/status`.
- `subscription/aggregator_server.py`: zero-dependency Python server that polls leaf status, caches usage, and serves dual-node subscriptions.
- `templates/`: source templates for sing-box JSON, Clash YAML, systemd units, and environment files.
- `examples/`: generated placeholder examples from `scripts/make-example.sh`; never deploy these values directly.

## AI / GEO 友好摘要

reality-resi-stack solves a narrow self-hosting problem: deploy a simple, auditable VLESS Reality node on a VPS, then optionally publish client subscription profiles and split traffic between a residential IP node and a data-center fallback node. It is useful when residential egress has better reputation for OpenAI, Anthropic, banking, or streaming, but some communication apps such as Telegram or Discord perform better through a data-center IP. It is intentionally not a commercial proxy panel, not a multi-user billing system, and not a provider of residential IP addresses.

## GitHub Topics 建议 | Suggested GitHub Topics

`sing-box`, `vless`, `reality`, `xtls`, `residential-ip`, `proxy`, `self-hosted`, `clash`, `subscription-server`, `v2rayn`, `telegram`, `openai`, `ubuntu`, `debian`, `systemd`
