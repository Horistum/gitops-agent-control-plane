#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POLICY="$ROOT/policy.json"
WORK="$HOME/.local/state/agent-control-plane"
SERVICE="agent-control-plane.service"
JOURNAL_LINES=80

usage() {
  cat <<'EOF'
Usage: scripts/diagnose-linux.sh [--policy FILE] [--work DIR] [--journal-lines N]

Read-only diagnostics. It never changes GitHub, controller state, policy or systemd configuration.
EOF
}
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 2; }
section(){ printf '\n## %s\n' "$*"; }
run_optional(){ printf '$ '; printf '%q ' "$@"; printf '\n'; "$@" || printf '[exit=%s]\n' "$?"; }

while (($#)); do
  case "$1" in
    --policy) [[ $# -ge 2 ]] || die "--policy needs a value"; POLICY="$2"; shift 2 ;;
    --work) [[ $# -ge 2 ]] || die "--work needs a value"; WORK="$2"; shift 2 ;;
    --journal-lines) [[ $# -ge 2 && "$2" =~ ^[0-9]+$ ]] || die "--journal-lines needs an integer"; JOURNAL_LINES="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

section "Host"
printf 'user=%s uid=%s kernel=%s arch=%s\n' "$(id -un)" "$(id -u)" "$(uname -sr)" "$(uname -m)"
run_optional df -h "$HOME"

section "Toolchain"
for cmd in git gh python3 podman systemctl codex; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf '%-10s %s\n' "$cmd" "$(command -v "$cmd")"
  else
    printf '%-10s MISSING\n' "$cmd"
  fi
done
command -v python3 >/dev/null 2>&1 && run_optional python3 --version
command -v gh >/dev/null 2>&1 && run_optional gh auth status --hostname github.com
command -v podman >/dev/null 2>&1 && run_optional podman info --format '{{json .Host.Security}}'
command -v codex >/dev/null 2>&1 && run_optional codex --version

section "Reference integrity"
run_optional python3 "$ROOT/scripts/validate_reference.py"

section "Policy"
if [[ -f "$POLICY" && ! -L "$POLICY" ]]; then
  printf 'policy=%s mode=%s\n' "$POLICY" "$(stat -c '%a' "$POLICY" 2>/dev/null || true)"
  run_optional python3 -m json.tool "$POLICY"
else
  printf 'policy not found: %s\n' "$POLICY"
fi

section "Service"
run_optional systemctl --user status "$SERVICE" --no-pager -l
run_optional systemctl --user show "$SERVICE" -p LoadState -p ActiveState -p SubState -p WorkingDirectory -p ExecStart --no-pager

section "Recent service log"
run_optional journalctl --user -u "$SERVICE" -n "$JOURNAL_LINES" --no-pager

section "Local state"
if [[ -d "$WORK" ]]; then
  printf 'work=%s\n' "$WORK"
  find "$WORK" -maxdepth 2 -type f -printf '%M %10s %TY-%Tm-%Td %TH:%TM %p\n' 2>/dev/null | sort | tail -80
else
  printf 'work directory not found: %s\n' "$WORK"
fi
