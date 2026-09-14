#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIN_FREE_GB="${AGENT_CONTROL_MIN_FREE_GB:-8}"

usage() {
  cat <<'EOF'
Usage:
  scripts/bootstrap-linux.sh check
  scripts/bootstrap-linux.sh prepare [--yes]
  scripts/bootstrap-linux.sh self-test

check      Read-only host prerequisite check.
prepare    Install supported Linux packages and prepare rootless Podman/systemd user services.
self-test  Exercise pure platform-detection logic without changing the host.

The script intentionally does not install or authenticate a model/runtime-specific CLI.
That belongs to the pinned runtime adapter and is validated during runtime installation.
EOF
}

die() { printf 'ERROR: %s\n' "$*" >&2; exit 2; }
note() { printf '==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

require_unprivileged() {
  [[ "${EUID}" -ne 0 ]] || die "run as the dedicated unprivileged controller user, never as root"
}

read_os_release() {
  [[ -r /etc/os-release ]] || die "cannot read /etc/os-release"
  . /etc/os-release
  printf '%s\n' "${ID:-unknown}" "${ID_LIKE:-}"
}

detect_pkg_manager_values() {
  local id="${1,,}" like="${2,,}"
  if [[ "$id" == "ubuntu" || "$id" == "debian" || "$like" == *"debian"* ]]; then
    printf 'apt\n'
  elif [[ "$id" == "fedora" || "$id" == "rhel" || "$id" == "rocky" || "$id" == "almalinux" || "$like" == *"rhel"* || "$like" == *"fedora"* ]]; then
    printf 'dnf\n'
  else
    return 1
  fi
}

detect_pkg_manager() {
  local os id like
  mapfile -t os < <(read_os_release)
  id="${os[0]}"
  like="${os[1]:-}"
  detect_pkg_manager_values "$id" "$like" || die "unsupported Linux distribution: ID=$id ID_LIKE=$like"
}

sudo_cmd() {
  if have sudo; then
    sudo "$@"
  else
    die "sudo is required for package provisioning"
  fi
}

install_packages() {
  local pm="$1"
  if [[ "$pm" == "apt" ]]; then
    sudo_cmd apt-get update
    sudo_cmd env DEBIAN_FRONTEND=noninteractive apt-get install -y \
      git curl ca-certificates jq python3 python3-venv python3-pip \
      podman uidmap slirp4netns fuse-overlayfs dbus-user-session \
      gh tar gzip xz-utils unzip zip
  elif [[ "$pm" == "dnf" ]]; then
    sudo_cmd dnf install -y \
      git curl ca-certificates jq python3 python3-pip \
      podman shadow-utils slirp4netns fuse-overlayfs \
      gh tar gzip xz unzip zip
  else
    die "internal error: unsupported package manager $pm"
  fi
}

ensure_subids() {
  local user="${USER:-$(id -un)}"
  if [[ -r /etc/subuid ]] && ! grep -qE "^${user}:" /etc/subuid; then
    note "creating subordinate UID range for rootless containers"
    sudo_cmd usermod --add-subuids 100000-165535 "$user"
  fi
  if [[ -r /etc/subgid ]] && ! grep -qE "^${user}:" /etc/subgid; then
    note "creating subordinate GID range for rootless containers"
    sudo_cmd usermod --add-subgids 100000-165535 "$user"
  fi
}

ensure_linger() {
  local user="${USER:-$(id -un)}"
  if have loginctl; then
    sudo_cmd loginctl enable-linger "$user"
  fi
}

free_gb() {
  local target="${1:-$HOME}"
  df -Pk "$target" | awk 'NR==2 {printf "%d\n", $4/1024/1024}'
}

check_systemd_user() {
  have systemctl || return 1
  systemctl --user show-environment >/dev/null 2>&1
}

check_podman_rootless() {
  have podman || return 1
  [[ "$(podman info --format '{{.Host.Security.Rootless}}' 2>/dev/null || true)" == "true" ]]
}

check_host() {
  require_unprivileged
  [[ "$(uname -s)" == "Linux" ]] || die "Linux is required"
  local pm
  pm="$(detect_pkg_manager)"
  printf 'platform: %s (%s)\n' "$(uname -m)" "$pm"

  local missing=()
  local cmd
  for cmd in git curl jq python3 podman gh systemctl; do
    have "$cmd" || missing+=("$cmd")
  done
  if ((${#missing[@]})); then
    printf 'missing commands: %s\n' "${missing[*]}" >&2
    return 1
  fi

  local free
  free="$(free_gb "$HOME")"
  printf 'free space under home filesystem: %s GiB\n' "$free"
  (( free >= MIN_FREE_GB )) || {
    printf 'need at least %s GiB free\n' "$MIN_FREE_GB" >&2
    return 1
  }

  check_systemd_user || {
    printf 'systemd user manager is unavailable; log in normally and enable linger\n' >&2
    return 1
  }

  check_podman_rootless || {
    printf 'Podman is not rootless/ready; a logout/login may be required after subuid/subgid changes\n' >&2
    return 1
  }

  if gh auth status --hostname github.com >/dev/null 2>&1; then
    printf 'GitHub CLI authentication: ok\n'
  else
    printf 'GitHub CLI authentication: not configured (run: gh auth login --hostname github.com)\n'
  fi

  if have codex; then
    printf 'runtime model CLI: %s\n' "$(codex --version 2>/dev/null || printf 'installed but version query failed')"
  else
    printf 'runtime model CLI: not installed; install the CLI required by COMPATIBILITY.json/runtime adapter before live installation\n'
  fi

  printf 'host prerequisite check: ok\n'
}

self_test() {
  [[ "$(detect_pkg_manager_values ubuntu '')" == "apt" ]] || die "ubuntu mapping failed"
  [[ "$(detect_pkg_manager_values debian '')" == "apt" ]] || die "debian mapping failed"
  [[ "$(detect_pkg_manager_values fedora '')" == "dnf" ]] || die "fedora mapping failed"
  [[ "$(detect_pkg_manager_values rocky 'rhel fedora')" == "dnf" ]] || die "rhel-like mapping failed"
  if detect_pkg_manager_values arch '' >/dev/null 2>&1; then
    die "unsupported distribution unexpectedly accepted"
  fi
  [[ "$MIN_FREE_GB" =~ ^[0-9]+$ ]] || die "AGENT_CONTROL_MIN_FREE_GB must be an integer"
  printf 'bootstrap self-test: ok\n'
}

main() {
  local command="${1:-check}"
  shift || true
  case "$command" in
    -h|--help|help) usage ;;
    self-test) [[ $# -eq 0 ]] || die "self-test accepts no arguments"; self_test ;;
    check) [[ $# -eq 0 ]] || die "check accepts no arguments"; check_host ;;
    prepare)
      local yes=0
      while (($#)); do
        case "$1" in
          --yes) yes=1 ;;
          -h|--help) usage; return 0 ;;
          *) die "unknown prepare option: $1" ;;
        esac
        shift
      done
      require_unprivileged
      local pm
      pm="$(detect_pkg_manager)"
      if (( ! yes )); then
        printf 'This will install host packages with sudo and enable user lingering. Continue [y/N]? '
        read -r answer
        [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]] || die "cancelled"
      fi
      install_packages "$pm"
      ensure_subids
      ensure_linger
      note "OS prerequisites installed"
      if ! check_host; then
        cat >&2 <<'EOF'
Host packages were installed, but rootless Podman/systemd is not ready yet.
Log out and back in once, then run:
  ./scripts/bootstrap-linux.sh check
EOF
        exit 3
      fi
      cat <<'EOF'

Linux host preparation is complete.
Next:
  1. authenticate GitHub: gh auth login --hostname github.com
  2. install/authenticate the model CLI required by the selected runtime adapter
  3. run: ./scripts/agentctl validate
  4. continue with docs/ADOPTION.md or docs/LINUX.md
EOF
      ;;
    *) die "unknown command: $command" ;;
  esac
}

main "$@"
