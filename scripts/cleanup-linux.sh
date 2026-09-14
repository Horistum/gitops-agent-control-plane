#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="$ROOT/.demo"
YES=0

usage() {
  cat <<'EOF'
Usage: scripts/cleanup-linux.sh [--yes]

Removes only local standalone-demo artifacts under .demo/.
It never changes Git history, remote repositories, credentials, or product source.
EOF
}

while (($#)); do
  case "$1" in
    --yes) YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done

if [[ ! -e "$TARGET" ]]; then
  printf 'No demo artifacts to remove.\n'
  exit 0
fi

if (( ! YES )); then
  printf 'Remove local demo artifacts at %s [y/N]? ' "$TARGET"
  read -r answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || {
    printf 'Cancelled.\n'
    exit 1
  }
fi

rm -rf -- "$TARGET"
printf 'Removed local demo artifacts. Repository source was preserved.\n'
