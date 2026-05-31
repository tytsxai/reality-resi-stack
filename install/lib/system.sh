#!/usr/bin/env bash
# system.sh — OS preflight, base packages, network tuning, firewall, fail2ban.
# Idempotent. Source this file; do not execute directly.

# shellcheck source=./common.sh
[[ -n "${COMMON_SH_LOADED:-}" ]] || {
  echo "system.sh: source common.sh first" >&2
  exit 1
}

# ── Preflight ────────────────────────────────────────────────────────────
phase_preflight() {
  step "Preflight"

  require_root

  if [[ ! -r /etc/os-release ]]; then
    die "Unsupported OS: /etc/os-release missing"
  fi
  # shellcheck source=/dev/null
  . /etc/os-release
  case "${ID:-}" in
    ubuntu | debian) ok "OS: ${PRETTY_NAME:-$ID}" ;;
    *) die "Unsupported OS (${ID:-?}). Supported: Ubuntu 22.04+, Debian 12+." ;;
  esac

  if ! command -v curl >/dev/null 2>&1; then
    warn "curl missing — will install"
  fi

  if [[ -n "${INBOUND_PORT:-}" ]] && port_in_use "$INBOUND_PORT"; then
    if ! ss -tlnp 2>/dev/null | awk -v p=":$INBOUND_PORT" '$0~p' | grep -q sing-box; then
      die "Port $INBOUND_PORT in use by something other than sing-box. Free it first."
    fi
    warn "Port $INBOUND_PORT already held by sing-box (will be reconfigured in place)"
  fi

  # Detect a prior MANUAL sing-box install. apt installing a second copy
  # creates a conflicting binary + systemd unit + config dir that will
  # silently break on next reboot. Refuse with a clear message.
  if [[ -x /usr/local/bin/sing-box && ! -e /usr/bin/sing-box ]]; then
    die "Detected an existing manually-installed sing-box at /usr/local/bin/sing-box.
This installer uses the official Sagernet apt repo and would create a second,
conflicting binary at /usr/bin/sing-box plus its own sing-box.service unit.
Refusing to proceed.

Options:
  1. Remove the manual install first:
       systemctl stop <your-custom-sing-box-unit>.service
       rm /usr/local/bin/sing-box
     Then re-run this installer.

  2. Keep your existing manual install and ignore this installer for sing-box.
     You can still use this repo's templates and subscription server manually."
  fi

  # Detect a foreign systemd unit managing sing-box under a different name.
  local foreign_units
  foreign_units="$(systemctl list-unit-files --type=service 2>/dev/null |
    awk '/sing-box.*\.service/ {print $1}' |
    grep -v '^sing-box\.service$' || true)"
  if [[ -n "$foreign_units" ]]; then
    die "Detected pre-existing sing-box systemd unit(s) under a non-default name:
$foreign_units

This installer manages sing-box via the default 'sing-box.service' unit.
Running it alongside another unit would race on ports and config paths.
Either disable/remove those units first, or do not install via this script."
  fi

  local mem_kib
  mem_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  if ((mem_kib < 400 * 1024)); then
    warn "Low RAM (${mem_kib} kiB). 512 MiB+ recommended; swap will be added."
  fi

  ok "Preflight done"
}

# ── Base packages ────────────────────────────────────────────────────────
phase_system_init() {
  step "Installing base packages"

  run env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  run env DEBIAN_FRONTEND=noninteractive apt-get -y -qq install \
    curl wget ca-certificates gnupg lsb-release unzip jq uuid-runtime \
    ufw fail2ban chrony python3 iproute2

  if [[ -n "${TIMEZONE:-}" ]]; then
    run timedatectl set-timezone "$TIMEZONE"
    ok "Timezone: $TIMEZONE"
  fi

  step "Enabling BBR + TCP fast open + MTU probing"
  write_file /etc/sysctl.d/99-bbr.conf 0644 <<'EOF'
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.tcp_fastopen=3
net.ipv4.tcp_mtu_probing=1
EOF
  run sysctl --system >/dev/null
  if [[ "$DRY_RUN" != "1" ]]; then
    local cc
    cc="$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null || true)"
    [[ "$cc" == "bbr" ]] && ok "BBR active" || warn "BBR requested but current cc=$cc"
  fi

  step "Adding 2 GiB swap (if absent)"
  if [[ ! -f /swapfile ]]; then
    run fallocate -l 2G /swapfile
    run chmod 600 /swapfile
    run mkswap /swapfile >/dev/null
    run swapon /swapfile
    ensure_line "/swapfile none swap sw 0 0" /etc/fstab
    ok "Swap added"
  else
    info "/swapfile exists — skip"
  fi
  write_file /etc/sysctl.d/99-swap-tuning.conf 0644 <<'EOF'
vm.swappiness=10
EOF
  run sysctl --system >/dev/null

  step "Limiting journald log volume"
  write_file /etc/systemd/journald.conf.d/99-limits.conf 0644 <<'EOF'
[Journal]
SystemMaxUse=100M
SystemKeepFree=500M
MaxRetentionSec=14day
Compress=yes
EOF
  svc_restart systemd-journald

  step "Enabling chrony (time sync)"
  svc_enable_now chrony

  ok "System init done"
}

# ── Firewall ─────────────────────────────────────────────────────────────
phase_firewall() {
  step "Configuring UFW"

  run ufw default deny incoming
  run ufw default allow outgoing
  run ufw allow "${INBOUND_PORT}/tcp"
  if [[ -n "${SSH_PORT:-}" ]]; then
    run ufw allow "${SSH_PORT}/tcp"
  fi
  if [[ "${WITH_SUBSCRIPTION:-0}" == "1" || "${WITH_AGGREGATOR:-0}" == "1" ]]; then
    run ufw allow 80/tcp
  fi
  run ufw --force enable
  ok "UFW configured"

  step "Configuring fail2ban (sshd jail)"
  local jail="/etc/fail2ban/jail.d/sshd.local"
  write_file "$jail" 0644 <<EOF
[sshd]
enabled = true
port = ${SSH_PORT:-22}
backend = systemd
maxretry = 5
findtime = 10m
bantime = 1h
EOF
  svc_enable_now fail2ban
  svc_restart fail2ban
  ok "fail2ban configured"
}

# ── Optional: SSH hardening ──────────────────────────────────────────────
# Only runs when --harden-ssh was passed. Prints loud warnings.
phase_ssh_hardening() {
  step "SSH hardening (--harden-ssh)"
  warn "Make sure you have a working SSH session in another window before continuing."
  warn "Misconfigured SSH can lock you out of the server."

  write_file /etc/ssh/sshd_config.d/99-root-keyonly.conf 0644 <<'EOF'
PermitRootLogin prohibit-password
PubkeyAuthentication yes
EOF

  if [[ -n "${SSH_PORT:-}" && "$SSH_PORT" != "22" ]]; then
    if grep -q '^Port ' /etc/ssh/sshd_config 2>/dev/null; then
      run sed -i "s/^Port .*/Port ${SSH_PORT}/" /etc/ssh/sshd_config
    else
      ensure_line "Port ${SSH_PORT}" /etc/ssh/sshd_config
    fi
    ok "SSH port -> ${SSH_PORT}"
  fi

  if [[ "$DRY_RUN" != "1" ]]; then
    sshd -t || die "sshd config test failed; aborting before reload"
  fi
  run systemctl reload ssh 2>/dev/null || run systemctl reload sshd
  ok "SSH reloaded"
}
