#!/usr/bin/env bash
# reality-resi-stack installer.
#
# Quick install:
#   bash <(curl -fsSL https://raw.githubusercontent.com/tytsxai/reality-resi-stack/main/install/install.sh) \
#     --node-name "US-Resi-01" --sni addons.mozilla.org
#
# Flags:
#   --node-name NAME            Display name shown in clients (required)
#   --sni HOST                  Reality SNI (default: addons.mozilla.org)
#   --inbound-port N            Listen port (default: 443)
#   --ssh-port N                SSH port if you want UFW to keep it open (default: 22)
#   --timezone TZ               e.g. America/Los_Angeles (optional)
#   --interface NAME            NIC for traffic accounting (default: auto-detect)
#   --total-bytes N             Plan quota for the subscription card (default: 0 = hide)
#   --billing-cycle-day N       Provider reset day for usage accounting (default: 1)
#   --usage-poll-interval N     Background usage sample interval seconds (default: 60)
#   --with-subscription         Install the subscription leaf server on :80
#   --with-aggregator URL       Install aggregator instead, polling URL for /status
#   --harden-ssh                Apply SSH key-only + port change (read warnings!)
#   --singbox-version X.Y.Z     Pin sing-box version (default: apt latest stable)
#   --dry-run                   Print every action, change nothing
#   --non-interactive           Refuse to prompt (use with --config)
#   --config FILE               Source a file with all the above as KEY=VALUE
#   --uninstall                 Tear down (calls uninstall.sh)
#   --help                      This message
#
# Environment:
#   REALITY_RESI_STACK_REF      Branch/tag for remote-piped installs (default: main)

set -Eeuo pipefail

# ── Self-locate the repo (handles both clone-and-run and curl-piped use) ─
REPO_DIR=/opt/reality-resi-stack
REALITY_RESI_STACK_REF="${REALITY_RESI_STACK_REF:-main}"
SCRIPT_PATH="${BASH_SOURCE[0]:-}"

# When invoked via `bash <(curl ...)`, BASH_SOURCE is /dev/fd/<n> — we need
# to fetch the full repo before we can source lib/*.sh and read templates/.
if [[ -z "$SCRIPT_PATH" || "$SCRIPT_PATH" == /dev/fd/* || "$SCRIPT_PATH" == /proc/* ]]; then
  echo ">> Detected remote-piped run — fetching ref ${REALITY_RESI_STACK_REF} to $REPO_DIR…"
  if ! command -v git >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq git
  fi
  if [[ -d "$REPO_DIR/.git" ]]; then
    git -C "$REPO_DIR" fetch --depth 1 origin "$REALITY_RESI_STACK_REF"
    git -C "$REPO_DIR" reset --hard FETCH_HEAD
  else
    rm -rf "$REPO_DIR"
    git clone --depth 1 --branch "$REALITY_RESI_STACK_REF" \
      https://github.com/tytsxai/reality-resi-stack.git "$REPO_DIR"
  fi
  exec bash "$REPO_DIR/install/install.sh" "$@"
fi

REPO_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
export REPO_ROOT

COMMON_SH_LOADED=1
export COMMON_SH_LOADED
# shellcheck source=lib/common.sh
. "$REPO_ROOT/install/lib/common.sh"
# shellcheck source=lib/system.sh
. "$REPO_ROOT/install/lib/system.sh"
# shellcheck source=lib/singbox.sh
. "$REPO_ROOT/install/lib/singbox.sh"
# shellcheck source=lib/subscription.sh
. "$REPO_ROOT/install/lib/subscription.sh"
# shellcheck source=lib/backup.sh
. "$REPO_ROOT/install/lib/backup.sh"

# ── Defaults ─────────────────────────────────────────────────────────────
NODE_NAME=""
SNI="addons.mozilla.org"
INBOUND_PORT=443
SSH_PORT=22
TIMEZONE=""
INTERFACE=""
TOTAL_BYTES=0
EXPIRE_TS=0
USAGE_OFFSET_BYTES=0
BILLING_CYCLE_DAY=1
USAGE_POLL_INTERVAL_SECONDS=60
COUNT_CURRENT_BOOT_ON_INIT=true
UPDATE_INTERVAL_HOURS=24
CACHE_TTL_SECONDS=60
REMOTE_POLL_INTERVAL_SECONDS=60
REMOTE_TIMEOUT_SECONDS=3
REQUEST_TIMEOUT_SECONDS=10
WITH_SUBSCRIPTION=0
WITH_AGGREGATOR=0
REMOTE_STATUS_URL=""
HARDEN_SSH=0
SINGBOX_VERSION=""
DRY_RUN=0
NON_INTERACTIVE=0
DO_UNINSTALL=0
CONFIG_FILE=""

print_help() { sed -n '/^# reality-resi-stack installer\./,/^set -Eeuo/{ /^set -Eeuo/d; s/^# \{0,1\}//; p; }' "$0"; }

# ── Argument parsing ─────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --node-name)
      NODE_NAME="$2"
      shift 2
      ;;
    --sni)
      SNI="$2"
      shift 2
      ;;
    --inbound-port)
      INBOUND_PORT="$2"
      shift 2
      ;;
    --ssh-port)
      SSH_PORT="$2"
      shift 2
      ;;
    --timezone)
      TIMEZONE="$2"
      shift 2
      ;;
    --interface)
      INTERFACE="$2"
      shift 2
      ;;
    --total-bytes)
      TOTAL_BYTES="$2"
      shift 2
      ;;
    --billing-cycle-day)
      BILLING_CYCLE_DAY="$2"
      shift 2
      ;;
    --usage-poll-interval)
      USAGE_POLL_INTERVAL_SECONDS="$2"
      REMOTE_POLL_INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --with-subscription)
      WITH_SUBSCRIPTION=1
      shift
      ;;
    --with-aggregator)
      WITH_AGGREGATOR=1
      REMOTE_STATUS_URL="$2"
      shift 2
      ;;
    --harden-ssh)
      HARDEN_SSH=1
      shift
      ;;
    --singbox-version)
      SINGBOX_VERSION="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --non-interactive)
      NON_INTERACTIVE=1
      shift
      ;;
    --config)
      CONFIG_FILE="$2"
      shift 2
      ;;
    --uninstall)
      DO_UNINSTALL=1
      shift
      ;;
    -h | --help)
      print_help
      exit 0
      ;;
    *) die "Unknown arg: $1 (try --help)" ;;
  esac
done

if [[ -n "$CONFIG_FILE" ]]; then
  [[ -f "$CONFIG_FILE" ]] || die "Config file not found: $CONFIG_FILE"
  # shellcheck source=/dev/null
  . "$CONFIG_FILE"
fi

export DRY_RUN

if [[ "$DO_UNINSTALL" == "1" ]]; then
  exec bash "$REPO_ROOT/install/uninstall.sh"
fi

if [[ "$WITH_SUBSCRIPTION" == "1" && "$WITH_AGGREGATOR" == "1" ]]; then
  die "--with-subscription and --with-aggregator are mutually exclusive"
fi

require_binary_flag() {
  local name="$1" value="$2"
  [[ "$value" == "0" || "$value" == "1" ]] || die "$name must be 0 or 1, got: $value"
}

require_uint() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || die "$name must be a non-negative integer, got: $value"
}

require_int() {
  local name="$1" value="$2"
  [[ "$value" =~ ^-?[0-9]+$ ]] || die "$name must be an integer, got: $value"
}

require_port() {
  local name="$1" value="$2"
  require_uint "$name" "$value"
  ((value >= 1 && value <= 65535)) || die "$name must be between 1 and 65535, got: $value"
}

require_min_uint() {
  local name="$1" value="$2" min="$3"
  require_uint "$name" "$value"
  ((value >= min)) || die "$name must be >= $min, got: $value"
}

require_safe_label() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[A-Za-z0-9._\ -]+$ ]] ||
    die "$name may contain only letters, numbers, space, dot, underscore, or hyphen: $value"
}

require_safe_host() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[A-Za-z0-9.-]+$ && "$value" != .* && "$value" != *. ]] ||
    die "$name must be a hostname or IPv4 address without spaces or URL syntax: $value"
}

require_safe_interface() {
  local name="$1" value="$2"
  [[ "$value" =~ ^[A-Za-z0-9_.:-]+$ ]] ||
    die "$name has unsafe characters for /sys/class/net lookup: $value"
}

require_bool_word() {
  local name="$1" value="$2"
  case "$value" in
    1 | 0 | true | false | yes | no | TRUE | FALSE | YES | NO | True | False | Yes | No) ;;
    *) die "$name must be true/false/yes/no/1/0, got: $value" ;;
  esac
}

validate_config() {
  require_binary_flag WITH_SUBSCRIPTION "$WITH_SUBSCRIPTION"
  require_binary_flag WITH_AGGREGATOR "$WITH_AGGREGATOR"
  require_binary_flag HARDEN_SSH "$HARDEN_SSH"
  require_port INBOUND_PORT "$INBOUND_PORT"
  [[ -z "$SSH_PORT" ]] || require_port SSH_PORT "$SSH_PORT"
  require_uint TOTAL_BYTES "$TOTAL_BYTES"
  require_uint EXPIRE_TS "$EXPIRE_TS"
  require_int USAGE_OFFSET_BYTES "$USAGE_OFFSET_BYTES"
  require_uint BILLING_CYCLE_DAY "$BILLING_CYCLE_DAY"
  ((BILLING_CYCLE_DAY >= 1 && BILLING_CYCLE_DAY <= 28)) ||
    die "BILLING_CYCLE_DAY must be 1..28, got: $BILLING_CYCLE_DAY"
  require_min_uint USAGE_POLL_INTERVAL_SECONDS "$USAGE_POLL_INTERVAL_SECONDS" 5
  require_min_uint UPDATE_INTERVAL_HOURS "$UPDATE_INTERVAL_HOURS" 1
  require_min_uint CACHE_TTL_SECONDS "$CACHE_TTL_SECONDS" 5
  require_min_uint REMOTE_POLL_INTERVAL_SECONDS "$REMOTE_POLL_INTERVAL_SECONDS" 5
  require_min_uint REMOTE_TIMEOUT_SECONDS "$REMOTE_TIMEOUT_SECONDS" 1
  require_min_uint REQUEST_TIMEOUT_SECONDS "$REQUEST_TIMEOUT_SECONDS" 1
  require_bool_word COUNT_CURRENT_BOOT_ON_INIT "$COUNT_CURRENT_BOOT_ON_INIT"
  require_safe_label NODE_NAME "$NODE_NAME"
  require_safe_host SNI "$SNI"
  require_safe_interface INTERFACE "$INTERFACE"
  [[ "$DRY_RUN" == "1" || -n "$SERVER_IP" ]] ||
    die "SERVER_IP auto-detection failed; set SERVER_IP in --config and rerun"
  [[ -z "$SERVER_IP" ]] || require_safe_host SERVER_IP "$SERVER_IP"
  [[ -z "$SINGBOX_VERSION" || "$SINGBOX_VERSION" =~ ^[^[:space:]]+$ ]] ||
    die "SINGBOX_VERSION must not contain whitespace"
  if [[ "$WITH_AGGREGATOR" == "1" ]]; then
    [[ "$REMOTE_STATUS_URL" =~ ^https?://[^[:space:]]+$ ]] ||
      die "REMOTE_STATUS_URL must be an http(s) URL without spaces"
  fi
}

# ── Interactive fill-in for required ─────────────────────────────────────
if [[ -z "$NODE_NAME" ]]; then
  if [[ "$NON_INTERACTIVE" == "1" ]]; then
    die "--node-name required in --non-interactive mode"
  fi
  read -rp "Node display name (e.g. US-Resi-01): " NODE_NAME
  [[ -n "$NODE_NAME" ]] || die "Node name cannot be empty"
fi

# Auto-detect NIC if not provided.
if [[ -z "$INTERFACE" ]]; then
  INTERFACE="$(default_interface || true)"
  [[ -n "$INTERFACE" ]] || die "Could not auto-detect interface; pass --interface NAME"
fi

# Pick a sensible server IP for the rendered client profile (auto-detect).
SERVER_IP="${SERVER_IP:-$(curl -fsS https://api.ipify.org 2>/dev/null || echo "")}"
if [[ -z "$SERVER_IP" ]]; then
  warn "Could not auto-detect public IP. Set SERVER_IP=… or --config to render client profile."
fi

validate_config

export SERVER_IP NODE_NAME SNI INBOUND_PORT SSH_PORT TIMEZONE INTERFACE \
  TOTAL_BYTES EXPIRE_TS USAGE_OFFSET_BYTES WITH_SUBSCRIPTION WITH_AGGREGATOR \
  BILLING_CYCLE_DAY USAGE_POLL_INTERVAL_SECONDS COUNT_CURRENT_BOOT_ON_INIT \
  UPDATE_INTERVAL_HOURS CACHE_TTL_SECONDS REMOTE_POLL_INTERVAL_SECONDS \
  REMOTE_TIMEOUT_SECONDS REQUEST_TIMEOUT_SECONDS REMOTE_STATUS_URL \
  HARDEN_SSH SINGBOX_VERSION

# ── Run phases ───────────────────────────────────────────────────────────
phase_preflight
phase_system_init
phase_install_singbox
phase_generate_keys
phase_configure_singbox
phase_singbox_service
phase_firewall

[[ "$HARDEN_SSH" == "1" ]] && phase_ssh_hardening || true

if [[ "$WITH_AGGREGATOR" == "1" ]]; then
  phase_subscription_aggregator
elif [[ "$WITH_SUBSCRIPTION" == "1" ]]; then
  phase_subscription_leaf
fi

phase_backup
phase_verify

# ── Final summary ────────────────────────────────────────────────────────
printf "\n"
printf "%s╔══════════════════════════════════════════════════════════════╗%s\n" "$C_GREEN" "$C_RESET"
printf "%s║                  INSTALLATION COMPLETE  ✔                    ║%s\n" "$C_GREEN" "$C_RESET"
printf "%s╚══════════════════════════════════════════════════════════════╝%s\n" "$C_GREEN" "$C_RESET"

if [[ "$DRY_RUN" != "1" ]]; then
  printf "\n%sNode :%s %s\n" "$C_CYAN" "$C_RESET" "$NODE_NAME"
  printf "%sIP   :%s %s\n" "$C_CYAN" "$C_RESET" "${SERVER_IP:-<unknown>}"
  printf "%sPort :%s %s\n" "$C_CYAN" "$C_RESET" "$INBOUND_PORT"
  printf "%sSNI  :%s %s\n" "$C_CYAN" "$C_RESET" "$SNI"

  printf "\n%sClient vless:// link (save this — it will not be shown again):%s\n" "$C_YELLOW" "$C_RESET"
  printf "  vless://%s@%s:%s?encryption=none&flow=xtls-rprx-vision&security=reality&sni=%s&fp=chrome&pbk=%s&sid=%s&type=tcp#%s\n" \
    "$UUID" "$SERVER_IP" "$INBOUND_PORT" "$SNI" "$REALITY_PUBLIC_KEY" "$SHORT_ID" "$NODE_NAME"

  if [[ "$WITH_SUBSCRIPTION" == "1" || "$WITH_AGGREGATOR" == "1" ]]; then
    printf "\n%sSubscription URL:%s http://%s/%s\n" "$C_CYAN" "$C_RESET" "${SERVER_IP:-<host>}" "$SUB_TOKEN"
  fi

  printf "\n%sSecrets stored at /etc/reality-resi-stack/secrets.env (mode 600).%s\n" "$C_GRAY" "$C_RESET"
fi
