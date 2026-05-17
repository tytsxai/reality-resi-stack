# Security policy

## Threat model | 威胁模型

`reality-resi-stack` is a personal / small-team self-hosted proxy toolkit. Its threat model is:

| In scope | Out of scope |
|---|---|
| Server-side bash and Python correctness | Multi-tenant isolation |
| Supply-chain integrity (pinned sing-box GPG fingerprint, hash-only secret denylist) | Defense against state-level adversaries with traffic analysis |
| Secret hygiene (CI redact gate, mode-600 secrets.env, no plaintext in repo) | Hardening of arbitrary upstream packages |
| Reasonable default firewall, fail2ban, SSH hardening behind explicit `--harden-ssh` flag | TPM / hardware-attested boot |

This is a tool for individuals running their own VPS, not a hardened enterprise product.

中文：本项目的威胁模型是"个人/小团队自托管代理"。安全努力集中在服务端脚本与 Python 实现的正确性、供应链完整性（sing-box apt 源 GPG 指纹锁定）、凭证卫生（CI 哈希脱敏门禁、`secrets.env` 600 权限）、合理的防火墙与 fail2ban 缺省值。**不在范围**：多租户隔离、对抗国家级流量分析、硬件可信启动等。

## Secret handling | 凭证处理规范

**Never commit:** UUIDs, Reality private/public keys, subscription tokens, server IPs, `secrets.env`, `usage-state.json`, `usage-cache.json`, `*.tar.gz` config backups, SSH keys, or anything resembling a real credential.

**The CI gate (`scripts/redact.sh` + `.github/workflows/redact.yml`) enforces this** by:

- Maintaining a SHA-256 hash list (`scripts/.redact-denylist.sha256`) of known-leaked credentials from prior incidents — the hashes are *not* leaks because they're cryptographic one-way.
- Detecting unknown UUID-shape strings and 43-character base64url strings (the shape of Curve25519 Reality keys) that aren't in the placeholder allowlist.
- Rejecting forbidden filename patterns at PR time.

If you discover a credential leak, **do not** open a public issue. Instead, [open a draft security advisory](https://github.com/tytsxai/reality-resi-stack/security/advisories/new).

## Reporting vulnerabilities | 漏洞上报

Open a draft security advisory (preferred), or email the maintainer privately. **Do not** file public GitHub issues for unpatched vulnerabilities.

We acknowledge reports within 7 days. No bug bounty — this is a volunteer project.

## What we do NOT support | 我们不支持的场景

- Running with cleartext `secrets.env` in any repo or in dotfiles
- Disabling the `--harden-ssh` warnings without keeping a parallel SSH session
- Sharing one UUID across multiple servers (regenerate per host)
- Restoring `usage-state.json` from one machine onto another (each leaf must maintain its own)
- Using `latest` sing-box tag in production (CI bumps the pinned version after testing)
