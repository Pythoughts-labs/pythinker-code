#!/usr/bin/env bash
set -euo pipefail

# Compatibility shim. Native installer is now canonical.
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P || true)"
if [ -n "$script_dir" ] && [ -f "$script_dir/install-native.sh" ]; then
  exec bash "$script_dir/install-native.sh" "$@"
fi

if command -v curl >/dev/null 2>&1; then
  curl -fsSL https://pythinker.com/install.sh | bash -s -- "$@"
elif command -v wget >/dev/null 2>&1; then
  wget -qO- https://pythinker.com/install.sh | bash -s -- "$@"
else
  echo "need curl or wget to fetch https://pythinker.com/install.sh" >&2
  exit 1
fi
