# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
- pytest harness for subscription servers (cache rollover, state-file recovery)

### v2 (not committed)

- Optional automated SNI rotation
- Optional Cloudflare WARP-style ECH support if sing-box stable adds it
- Three-node mesh aggregator
