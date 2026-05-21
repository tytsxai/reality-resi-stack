#!/usr/bin/env bash
# backup.sh — install a daily systemd timer that tarballs configuration
# (NOT logs, NOT secrets, NOT runtime state).

# shellcheck source=./common.sh
[[ -n "${COMMON_SH_LOADED:-}" ]] || {
  echo "backup.sh: source common.sh first" >&2
  exit 1
}

phase_backup() {
  step "Installing daily config backup timer"

  write_file /usr/local/sbin/backup-reality-resi-stack.sh 0755 <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail

BACKUP_DIR=/var/backups/reality-resi-stack
STAMP="$(date +%Y-%m-%d-%H%M%S)"
OUT="$BACKUP_DIR/reality-resi-stack-${STAMP}.tar.gz"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
{
  echo "created_at=$(date -Is)"
  echo "hostname=$(hostname)"
  echo "kernel=$(uname -r)"
  echo "timezone=$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  systemctl show sing-box -p ActiveState -p SubState -p NRestarts 2>/dev/null || true
  ufw status verbose 2>/dev/null || true
  ss -tlnp 2>/dev/null || true
} > "$TMP/manifest.txt"

tar -czf "$OUT" -C / --ignore-failed-read \
  --exclude=var/lib/reality-resi-stack/usage-state.json \
  --exclude=var/lib/reality-resi-stack/usage-cache.json \
  etc/sing-box \
  etc/systemd/system/sing-box.service \
  etc/systemd/system/subscription-leaf.service \
  etc/systemd/system/subscription-aggregator.service \
  etc/reality-resi-stack \
  usr/local/lib/reality-resi-stack \
  var/lib/reality-resi-stack \
  etc/ufw \
  etc/fail2ban \
  etc/sysctl.d \
  etc/systemd/journald.conf.d \
  "$TMP/manifest.txt"
chmod 600 "$OUT"

# Retain only the 3 most recent backups.
find "$BACKUP_DIR" -name 'reality-resi-stack-*.tar.gz' -type f \
  | sort | head -n -3 | xargs -r rm -f

echo "$OUT"
EOF

  run cp "$REPO_ROOT/templates/systemd/config-backup.service" \
    /etc/systemd/system/reality-resi-stack-backup.service
  run cp "$REPO_ROOT/templates/systemd/config-backup.timer" \
    /etc/systemd/system/reality-resi-stack-backup.timer
  run systemctl daemon-reload
  run systemctl enable --now reality-resi-stack-backup.timer
  ok "Backup timer installed"
}
