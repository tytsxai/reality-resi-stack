# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Leaf subscription accounting now keeps usage fresher by sampling in the background every `USAGE_POLL_INTERVAL_SECONDS` seconds instead of only updating when a client pulls the subscription URL.
- Leaf subscription accounting now supports provider billing reset days via `BILLING_CYCLE_DAY`, so plans that reset on the 11th do not roll over on the 1st by mistake.
- Leaf subscription accounting now counts bytes already present in the current boot on first state creation by default (`COUNT_CURRENT_BOOT_ON_INIT=true`), while still supporting baseline-only mode and `USAGE_OFFSET_BYTES` calibration.
- Leaf accounting now carries usage forward across reboots or NIC counter rollovers by adding the new boot's current counter instead of silently dropping it.
- Aggregator subscription accounting now refreshes the leaf status cache in the background via `REMOTE_POLL_INTERVAL_SECONDS`, keeping usage cards warm even before the next client request.
- Re-running the installer with an existing `secrets.env` re-exports the reused UUID, Reality keys, subscription token, and short ID before rendering templates.
- `--with-subscription` and `--with-aggregator` are now mutually exclusive, and aggregator installs fail early unless the residential-node template variables are provided.

### Added

- `REALITY_RESI_STACK_REF` lets remote-piped installs fetch a specific branch or tag while defaulting to `main`.
- Standard-library `unittest` coverage for leaf accounting and aggregator cache fallback, wired into `make test` and GitHub Actions.
- `make mdcheck` now falls back to `npx --yes markdown-link-check` when the binary is not installed globally, retries transient link-checker failures once, and GitHub Actions runs the same Markdown link gate.

### Security

- Subscription systemd units now use basic sandboxing (`NoNewPrivileges`, `PrivateTmp`, `ProtectHome`, `ProtectSystem=strict`) and only keep `/var/lib/reality-resi-stack` writable.
- Config backups now exclude runtime usage/cache state, set backup directory permissions to `700`, and write archives as `600`.

## [1.0.3] — 2026-05-19

### Added (Documentation)

- **`llms.txt`** — AI-search-engine index covering what the toolkit does, what it does NOT do, common questions ("Why is Telegram slow on residential IP?", "Why does OpenAI block my data-center VPS?"), and long-tail search phrases (residential IP VLESS, ChatGPT 住宅 IP 出口, Telegram 住宅 IP 卡顿, etc.).
- **README — FAQ section** with 7 Q&As covering the residential-vs-data-center dichotomy, idempotent re-runs, Reality-no-domain, 3x-ui/XHTTP-Installer comparison, and GPL-3.0 implications.
- **README — Keywords block + nav row** (Release / Docs / llms.txt / Changelog / Issues).

### Notes

Documentation-only release. Installer behavior is unchanged from v1.0.2; users running v1.0.2 do not need to re-deploy.

## [1.0.2] — 2026-05-17

### Added

- `phase_preflight` now refuses to proceed if it detects a pre-existing manual sing-box install (`/usr/local/bin/sing-box` present without the apt-managed `/usr/bin/sing-box`) **or** a foreign systemd unit matching `sing-box*.service` other than the default `sing-box.service`. Without this check, `apt install sing-box` silently adds a second binary and a second systemd unit alongside the existing manual install — both apparently inactive at install time, but the next reboot or any `systemctl start sing-box` would race against the user's working unit on ports 443/8443 and config paths. Caught the hard way by attempting v1.0.1 verification against a real production host that turned out to already host a manually-installed sing-box.

## [1.0.1] — 2026-05-17

### Fixed

- **Critical**: pinned `SINGBOX_APT_KEY_FPR` in `install/lib/singbox.sh` was a placeholder that did not match the real Sagernet GPG key bundle, causing **every real install to fail at `phase_install_singbox`** with a fingerprint-mismatch abort. Bug was not caught by `--dry-run` because dry-run intentionally skips the GPG check. Now pinned to the primary fingerprint `2C317FBD5D886B4E89BAE8DA6D9152172A2B2F0C` and verified against the live key file on Ubuntu 24.04 LTS.
- **Critical**: `phase_verify` ran live `systemctl` / `ss` / `sing-box check` calls in `--dry-run` mode, producing fake-looking failures and a non-zero installer exit even though nothing had been installed. Now correctly no-ops in dry-run.
- GPG verification logic now requires the pinned fingerprint to be **present anywhere in the bundle** rather than to be the first fingerprint — Sagernet bundles a primary key plus a signing subkey, so the first-fingerprint check was fragile against subkey rotation.

### Note for users of 1.0.0

v1.0.0 was withdrawn within an hour of publication due to the GPG fingerprint bug above — please use v1.0.1 or later. Sorry for the noise.

## [1.0.0] — 2026-05-17 (withdrawn)

Initial release. **Withdrawn** — see 1.0.1 changelog for the install-blocking bug found 30 minutes after publication.

### Added

- **Modular bash installer** (`install/install.sh` + 5 lib modules) for Ubuntu 22.04+ / Debian 12+. Phases: preflight → system tuning → sing-box install with verified GPG fingerprint → key generation → config render → systemd service → firewall (UFW + fail2ban) → optional SSH hardening → optional subscription server → backup timer → end-to-end verification. Idempotent, supports `--dry-run`, `--non-interactive`, `--config`.
- **VLESS + Reality + xtls-rprx-vision** server config templates (`templates/singbox/`) with no domain or TLS cert required.
- **Two Python subscription servers** (`subscription/leaf_server.py`, `subscription/aggregator_server.py`) — zero third-party dependencies, standard library only.
  - Leaf reads `/sys/class/net/<iface>/statistics/*_bytes` for monthly traffic accounting, emits `Subscription-Userinfo` / `Profile-Title` / `Profile-Update-Interval` headers.
  - Aggregator polls a leaf's `/status` endpoint, caches the result, and falls back to cached values during leaf outages (prevents "0 bytes used" jitter in client usage cards).
- **Smart routing Clash template** (`templates/clash/client-dual.yaml.tmpl`) for dual-node deployments:
  - Routes OpenAI / Anthropic / Claude / Google AI / Netflix / banking domains through the residential node (where residential-IP reputation is an asset).
  - Routes Telegram / Discord / messenger domains through the data-center node (avoiding the "residential IP soft-throttle" problem common to messenger services).
- **Hash-only secret denylist** (`scripts/.redact-denylist.sha256`) plus shape-based detector (`scripts/redact.sh`) — CI fails on any UUID, Reality key, or known-leaked IP.
- **Deterministic example generator** (`scripts/make-example.sh`) using RFC 5737 documentation IPs and sentinel UUIDs.
- **Daily systemd-timer backup** of configuration (excludes runtime state, secrets are mode-600).
- **Bilingual documentation**: 5 docs in `docs/zh-CN/` (DEPLOYMENT, SUBSCRIPTION, DUAL-NODE, TROUBLESHOOTING, CLIENTS) with English mirrors in `docs/en/`.
- **GitHub Actions CI**: shellcheck, shfmt, ruff, yamllint, jsonlint, plus the redact gate.

### Security

- sing-box apt repo signing key fingerprint pinned (`SINGBOX_APT_KEY_FPR`). Installer refuses to proceed on fingerprint mismatch — defense against supply-chain compromise.
- `secrets.env` written mode 600, owned by root.
- `.gitignore` aggressively blocks credential file patterns at the git layer; CI redact gate is the second line.

## Roadmap

### v1.1+ (community-demand-driven)

- Additional translations (Farsi, Russian, Arabic, Vietnamese, Turkish, Indonesian, Burmese, Spanish — based on issue requests)
- GitHub Pages site with proper sitemap + hreflang
- Asciinema cast of the installer flow

### v2 (not committed)

- Optional automated SNI rotation
- Optional Cloudflare WARP-style ECH support if sing-box stable adds it
- Three-node mesh aggregator
