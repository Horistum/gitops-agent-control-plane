#!/usr/bin/env bash
set -Eeuo pipefail

SERVICE="agent-control-plane.service"
UNIT="$HOME/.config/systemd/user/$SERVICE"
RUNTIME_BASE="$HOME/.local/share/agent-control-plane"
WORK="$HOME/.local/state/agent-control-plane"
PURGE_RUNTIME=0
PURGE_STATE=0
YES=0

usage() {
  cat <<'EOF'
Usage: scripts/uninstall-linux.sh [--purge-runtime] [--purge-state] [--yes]

Default action:
  - stop and disable agent-control-plane.service
  - remove only the local systemd unit installed by this reference

Optional destructive actions:
  --purge-runtime  remove ~/.local/share/agent-control-plane
  --purge-state    remove ~/.local/state/agent-control-plane
  --yes            skip the local confirmation prompt

This script never deletes GitHub repositories, issues, product branches, pull requests or the
remote authoritative state branch.
EOF
}
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 2; }

while (($#)); do
  case "$1" in
    --purge-runtime) PURGE_RUNTIME=1 ;;
    --purge-state) PURGE_STATE=1 ;;
    --yes) YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
  shift
done

[[ "${EUID}" -ne 0 ]] || die "run as the unprivileged controller user, never root"

printf 'Will disable local service: %s\n' "$SERVICE"
(( PURGE_RUNTIME )) && printf 'Will delete runtime directory: %s\n' "$RUNTIME_BASE"
(( PURGE_STATE )) && printf 'Will delete local state directory: %s\n' "$WORK"
printf 'Remote GitHub state will NOT be deleted.\n'

if (( ! YES )); then
  printf 'Continue [y/N]? '
  read -r answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || die "cancelled"
fi

systemctl --user disable --now "$SERVICE" >/dev/null 2>&1 || true
if [[ -f "$UNIT" ]]; then
  rm -f -- "$UNIT"
fi
systemctl --user daemon-reload >/dev/null 2>&1 || true
systemctl --user reset-failed "$SERVICE" >/dev/null 2>&1 || true

(( PURGE_RUNTIME )) && rm -rf -- "$RUNTIME_BASE"
(( PURGE_STATE )) && rm -rf -- "$WORK"

printf 'Local uninstall complete. Remote GitHub resources were preserved.\n'
