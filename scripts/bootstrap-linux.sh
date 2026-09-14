#!/usr/bin/env bash
set -Eeuo pipefail

MIN_FREE_GB="${AGENT_CONTROL_MIN_FREE_GB:-1}"
usage(){ cat <<'EOF'
Usage:
  scripts/bootstrap-linux.sh check
  scripts/bootstrap-linux.sh prepare [--yes]
  scripts/bootstrap-linux.sh self-test

The standalone showcase needs Linux, Bash, Git and Python 3.11+.
Automatic prepare intentionally does not install Python because distribution defaults vary.
EOF
}
die(){ printf 'ERROR: %s\n' "$*" >&2; exit 2; }
have(){ command -v "$1" >/dev/null 2>&1; }
detect_pkg_manager_values(){ local id="${1,,}" like="${2,,}"; if [[ "$id" == ubuntu || "$id" == debian || "$like" == *debian* ]]; then printf 'apt\n'; elif [[ "$id" == fedora || "$id" == rhel || "$id" == rocky || "$id" == almalinux || "$like" == *rhel* || "$like" == *fedora* ]]; then printf 'dnf\n'; else return 1; fi; }
detect_pkg_manager(){ [[ -r /etc/os-release ]] || die "cannot read /etc/os-release"; . /etc/os-release; detect_pkg_manager_values "${ID:-unknown}" "${ID_LIKE:-}" || die "unsupported automatic provisioning for ID=${ID:-unknown}; install Bash, Git and Python 3.11+ manually"; }
python_ok(){ have python3 || return 1; python3 -S - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}
free_gb(){ df -Pk "${1:-$HOME}" | awk 'NR==2 {printf "%d\n", $4/1024/1024}'; }
check_host(){
  [[ "$(uname -s)" == Linux ]] || die "Linux is required by this bootstrap helper"
  local missing=() cmd
  for cmd in bash git python3; do have "$cmd" || missing+=("$cmd"); done
  if ((${#missing[@]})); then printf 'ERROR: missing commands:' >&2; printf ' %s' "${missing[@]}" >&2; printf '\n' >&2; exit 2; fi
  python_ok || die "Python 3.11+ is required"
  local free; free="$(free_gb "$HOME")"; (( free >= MIN_FREE_GB )) || die "need at least ${MIN_FREE_GB} GiB free"
  printf 'Linux showcase prerequisites: ok\n'; printf 'bash: %s\n' "$(bash --version | head -1)"; printf 'git: %s\n' "$(git --version)"; printf 'python: %s\n' "$(python3 --version)"; printf 'free-home-gib: %s\n' "$free"
}
prepare(){
  local yes=0; [[ "${1:-}" == --yes ]] && yes=1; [[ $# -le 1 ]] || die "prepare accepts only --yes"
  python_ok || die "prepare requires Python 3.11+ to be installed first; distro default Python is not assumed"
  local pm; pm="$(detect_pkg_manager)"
  if (( ! yes )); then printf 'Install Bash/Git system prerequisites with sudo [y/N]? '; read -r answer; [[ "${answer,,}" == y || "${answer,,}" == yes ]] || die "cancelled"; fi
  have sudo || die "sudo is required for automatic provisioning"
  if [[ "$pm" == apt ]]; then sudo apt-get update; sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y bash git ca-certificates; else sudo dnf install -y bash git ca-certificates; fi
  check_host
}
self_test(){ [[ "$(detect_pkg_manager_values ubuntu '')" == apt ]]; [[ "$(detect_pkg_manager_values debian '')" == apt ]]; [[ "$(detect_pkg_manager_values fedora '')" == dnf ]]; [[ "$(detect_pkg_manager_values rocky 'rhel fedora')" == dnf ]]; if detect_pkg_manager_values arch '' >/dev/null 2>&1; then die "unsupported distribution unexpectedly accepted"; fi; [[ "$MIN_FREE_GB" =~ ^[0-9]+$ ]] || die "AGENT_CONTROL_MIN_FREE_GB must be an integer"; printf 'bootstrap self-test: ok\n'; }
case "${1:-check}" in check) shift || true; [[ $# -eq 0 ]] || die "check accepts no arguments"; check_host ;; prepare) shift || true; prepare "$@" ;; self-test) shift || true; [[ $# -eq 0 ]] || die "self-test accepts no arguments"; self_test ;; help|-h|--help) usage ;; *) die "unknown command: $1" ;; esac
