#!/usr/bin/env bash
# singbox.sh — install sing-box from official apt source, generate keys,
# render configuration, install systemd unit, run E2E verification.

# shellcheck source=./common.sh
[[ -n "${COMMON_SH_LOADED:-}" ]] || {
  echo "singbox.sh: source common.sh first" >&2
  exit 1
}

# Pinned GPG fingerprints of the Sagernet apt repository signing key bundle.
# Verified against https://sing-box.app/gpg.key on 2026-05-17 — the bundle
# contains a primary key plus a signing subkey, both with their own fingerprint.
# We require the EXPECTED fingerprint to be present anywhere in the bundle
# (not just first), so upstream subkey rotation does not break us.
# Override with SINGBOX_APT_KEY_FPR=<fpr> if you've pinned a newer rotation.
SINGBOX_APT_KEY_FPR="${SINGBOX_APT_KEY_FPR:-2C317FBD5D886B4E89BAE8DA6D9152172A2B2F0C}"

# ── Install sing-box from official apt repo ──────────────────────────────
phase_install_singbox() {
  step "Installing sing-box from Sagernet apt repo"

  run mkdir -p /etc/apt/keyrings
  if [[ ! -f /etc/apt/keyrings/sagernet.asc ]]; then
    run curl -fsSL https://sing-box.app/gpg.key -o /etc/apt/keyrings/sagernet.asc
    run chmod a+r /etc/apt/keyrings/sagernet.asc
  fi

  # Verify the expected fingerprint is in the bundle.
  if [[ "$DRY_RUN" != "1" ]]; then
    local all_fprs
    all_fprs="$(gpg --show-keys --with-colons /etc/apt/keyrings/sagernet.asc 2>/dev/null |
      awk -F: '$1=="fpr" {print $10}')"
    if ! grep -qxF "$SINGBOX_APT_KEY_FPR" <<<"$all_fprs"; then
      die "Sagernet GPG fingerprint mismatch.
Expected (any of): $SINGBOX_APT_KEY_FPR
Got bundle fingerprints:
$all_fprs
Refusing to install — possible supply-chain tampering. If Sagernet has rotated keys,
re-pin via: SINGBOX_APT_KEY_FPR=<new-fpr> bash install/install.sh ..."
    fi
    ok "GPG fingerprint verified: $SINGBOX_APT_KEY_FPR present in bundle"
  fi

  write_file /etc/apt/sources.list.d/sagernet.sources 0644 <<'EOF'
Types: deb
URIs: https://deb.sagernet.org/
Suites: *
Components: *
Enabled: yes
Signed-By: /etc/apt/keyrings/sagernet.asc
EOF

  run env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  run env DEBIAN_FRONTEND=noninteractive apt-get -y -qq install sing-box

  if [[ "$DRY_RUN" != "1" ]]; then
    sing-box version | head -1 | while read -r line; do ok "$line"; done
  fi
}

# ── Generate keys (writes secrets.env) ───────────────────────────────────
phase_generate_keys() {
  step "Generating per-server secrets"

  local secrets=/etc/reality-resi-stack/secrets.env

  if [[ -f "$secrets" ]]; then
    info "Secrets already exist at $secrets — reusing (will not regenerate)"
    # shellcheck source=/dev/null
    if [[ "$DRY_RUN" != "1" ]]; then
      . "$secrets"
      : "${UUID:?}" "${REALITY_PRIVATE_KEY:?}" "${REALITY_PUBLIC_KEY:?}" "${SUB_TOKEN:?}"
      SHORT_ID="${SHORT_ID:-}"
      export UUID REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY SUB_TOKEN SHORT_ID
    fi
    return 0
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    info "[dry] would write $secrets with new UUID, Reality keypair, SUB_TOKEN"
    UUID="00000000-0000-0000-0000-000000000000"
    REALITY_PRIVATE_KEY="AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    REALITY_PUBLIC_KEY="BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    SUB_TOKEN="example-token-do-not-use"
    SHORT_ID=""
    export UUID REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY SUB_TOKEN SHORT_ID
    return 0
  fi

  UUID="$(uuidgen)"
  local kp pri pub
  kp="$(sing-box generate reality-keypair)"
  pri="$(awk '/PrivateKey/ {print $2}' <<<"$kp")"
  pub="$(awk '/PublicKey/ {print $2}' <<<"$kp")"
  [[ -n "$pri" && -n "$pub" ]] || die "Reality keypair generation failed"
  REALITY_PRIVATE_KEY="$pri"
  REALITY_PUBLIC_KEY="$pub"
  SUB_TOKEN="$(uuidgen)"
  SHORT_ID="${SHORT_ID:-}"

  mkdir -p "$(dirname "$secrets")"
  {
    printf 'UUID=%s\n' "$UUID"
    printf 'REALITY_PRIVATE_KEY=%s\n' "$REALITY_PRIVATE_KEY"
    printf 'REALITY_PUBLIC_KEY=%s\n' "$REALITY_PUBLIC_KEY"
    printf 'SUB_TOKEN=%s\n' "$SUB_TOKEN"
    printf 'SHORT_ID=%s\n' "$SHORT_ID"
  } >"$secrets"
  chmod 600 "$secrets"
  ok "Secrets written to $secrets (mode 600)"

  export UUID REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY SUB_TOKEN SHORT_ID
}

# ── Render configuration ─────────────────────────────────────────────────
phase_configure_singbox() {
  step "Rendering sing-box configuration"

  : "${UUID:?}" "${REALITY_PRIVATE_KEY:?}" "${SNI:?}" "${INBOUND_PORT:?}"
  : "${SHORT_ID=}"

  local conf=/etc/sing-box/conf
  run mkdir -p "$conf" /etc/sing-box/logs

  local tpl="$REPO_ROOT/templates/singbox"
  run cp "$tpl/00_log.json" "$conf/00_log.json"
  run cp "$tpl/01_outbounds.json" "$conf/01_outbounds.json"
  run cp "$tpl/03_route.json" "$conf/03_route.json"
  run cp "$tpl/05_dns.json" "$conf/05_dns.json"
  run cp "$tpl/06_ntp.json" "$conf/06_ntp.json"

  render_template \
    "$tpl/11_xtls-reality_inbounds.json.tmpl" \
    "$conf/11_xtls-reality_inbounds.json" \
    0644

  if [[ "$DRY_RUN" != "1" ]]; then
    sing-box check -C "$conf" || die "sing-box config check failed"
    ok "Config validates"
  fi
}

# ── systemd unit ─────────────────────────────────────────────────────────
phase_singbox_service() {
  step "Installing sing-box systemd unit"
  run cp "$REPO_ROOT/templates/systemd/sing-box.service" \
    /etc/systemd/system/sing-box.service
  svc_enable_now sing-box
  ok "sing-box service enabled"
}

# ── End-to-end verification ──────────────────────────────────────────────
phase_verify() {
  step "End-to-end verification"

  if [[ "$DRY_RUN" == "1" ]]; then
    info "[dry] skipping verify — nothing was actually installed"
    return 0
  fi

  local fails=0

  if svc_is_active sing-box; then
    ok "sing-box is active"
  else
    fail "sing-box not active"
    fails=$((fails + 1))
  fi

  if ss -tlnp 2>/dev/null | grep -q ":${INBOUND_PORT} "; then
    ok "Listening on tcp/${INBOUND_PORT}"
  else
    fail "Not listening on tcp/${INBOUND_PORT}"
    fails=$((fails + 1))
  fi

  if sing-box check -C /etc/sing-box/conf >/dev/null 2>&1; then
    ok "sing-box check OK"
  else
    fail "sing-box check failed"
    fails=$((fails + 1))
  fi

  # TLS handshake self-test — confirms Reality is fronting the configured SNI.
  if command -v openssl >/dev/null 2>&1; then
    if echo | timeout 5 openssl s_client \
      -connect "127.0.0.1:${INBOUND_PORT}" \
      -servername "${SNI}" -verify_quiet 2>/dev/null |
      grep -q "subject="; then
      ok "TLS handshake to 127.0.0.1:${INBOUND_PORT} produced a certificate (Reality fronting works)"
    else
      warn "TLS self-handshake produced no cert — Reality may still be OK; verify from a real client"
    fi
  fi

  if [[ "${WITH_SUBSCRIPTION:-0}" == "1" || "${WITH_AGGREGATOR:-0}" == "1" ]]; then
    if curl -fsS "http://127.0.0.1/healthz" >/dev/null 2>&1; then
      ok "Subscription /healthz responds"
    else
      fail "Subscription /healthz does not respond"
      fails=$((fails + 1))
    fi
  fi

  if ((fails > 0)); then
    die "Verification: $fails check(s) failed"
  fi
  ok "All verification checks passed"
}
