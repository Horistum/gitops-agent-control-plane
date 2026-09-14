#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

usage() {
  cat <<'EOF'
Usage: scripts/diagnose-linux.sh

Read-only diagnostics for the standalone showcase.
EOF
}

case "${1:-}" in
  -h|--help|help) usage; exit 0 ;;
  "") ;;
  *) printf 'ERROR: unknown argument: %s\n' "$1" >&2; exit 2 ;;
esac

printf '## Host\n'
printf 'kernel=%s arch=%s\n' "$(uname -sr)" "$(uname -m)"
df -h "$HOME" || true

printf '\n## Toolchain\n'
for cmd in bash git python3; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf '%-8s %s\n' "$cmd" "$(command -v "$cmd")"
  else
    printf '%-8s MISSING\n' "$cmd"
  fi
done
git --version || true
python3 --version || true

printf '\n## Reference validation\n'
python3 "$ROOT/scripts/validate_reference.py" --fast

printf '\n## Demo artifacts\n'
if [[ -d "$ROOT/.demo/runs" ]]; then
  find "$ROOT/.demo/runs" -maxdepth 3 -name run-summary.json -print | sort | tail -20
else
  printf 'No demo runs yet. Run: ./scripts/agentctl demo happy-path\n'
fi
