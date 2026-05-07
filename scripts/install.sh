#!/usr/bin/env bash
set -euo pipefail

# Colors — match src/pythinker_code/ui/shell/__init__.py logo palette.
# Skip if stdout isn't a TTY or NO_COLOR is set.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  NAVY=$'\033[38;5;24m'
  FACE=$'\033[38;5;255m'
  CORAL=$'\033[38;5;216m'
  IRIS=$'\033[38;5;152m'
  DIM=$'\033[2m'
  BOLD=$'\033[1m'
  RESET=$'\033[0m'
  CLEAR_LINE=$'\r\033[K'
else
  NAVY=""; FACE=""; CORAL=""; IRIS=""; DIM=""; BOLD=""; RESET=""; CLEAR_LINE=""
fi

print_logo() {
  printf '\n'
  printf '      %s●%s\n'                                        "$CORAL" "$RESET"
  printf '      %s│%s\n'                                        "$NAVY"  "$RESET"
  printf '  %s▛%s%s▀▀▀▀▀▀▀%s%s▜%s\n'                            "$NAVY" "$RESET" "$FACE" "$RESET" "$NAVY" "$RESET"
  printf ' %s◖%s%s█%s %s◉%s   %s◉%s %s█%s%s◗%s\n'               "$CORAL" "$RESET" "$NAVY" "$RESET" "$IRIS" "$RESET" "$IRIS" "$RESET" "$NAVY" "$RESET" "$CORAL" "$RESET"
  printf '  %s▙▄▄▄%s%s≡%s%s▄▄▄▟%s\n'                            "$NAVY" "$RESET" "$FACE" "$RESET" "$NAVY" "$RESET"
  printf '\n'
  printf '  %s%spythinker code%s %s· your next CLI agent%s\n\n' "$BOLD" "$FACE" "$RESET" "$DIM" "$RESET"
}

step() { printf '  %s⠿%s %s\n' "$IRIS" "$RESET" "$1"; }
ok()   { printf '  %s✓%s %s\n' "$IRIS" "$RESET" "$1"; }
warn() { printf '  %s!%s %s\n' "$CORAL" "$RESET" "$1" >&2; }
fail() { printf '  %s✗%s %s\n' "$CORAL" "$RESET" "$1" >&2; exit 1; }

# Spinner around a long command. Streams the command's output to a tmpfile;
# on failure, replays it so the user can debug.
spin_run() {
  local label="$1"; shift
  if [ ! -t 1 ]; then
    step "$label"
    "$@"
    return
  fi
  local log
  log="$(mktemp)"
  trap 'rm -f "$log"' RETURN
  "$@" >"$log" 2>&1 &
  local pid=$!
  local frames='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local i=0
  while kill -0 "$pid" 2>/dev/null; do
    local f="${frames:$((i % ${#frames})):1}"
    printf '%s  %s%s%s %s' "$CLEAR_LINE" "$IRIS" "$f" "$RESET" "$label"
    i=$((i + 1))
    sleep 0.08
  done
  wait "$pid"
  local rc=$?
  if [ $rc -eq 0 ]; then
    printf '%s' "$CLEAR_LINE"
    ok "$label"
  else
    printf '%s' "$CLEAR_LINE"
    fail "$label"$'\n'"$(cat "$log")"
  fi
  rm -f "$log"
  return $rc
}

install_uv_quietly() {
  if command -v curl >/dev/null 2>&1; then
    spin_run "Fetching uv (Python package installer)" \
      bash -c 'curl -fsSL https://astral.sh/uv/install.sh | sh -s -- --quiet >/dev/null 2>&1 || curl -fsSL https://astral.sh/uv/install.sh | sh >/dev/null 2>&1'
    return
  fi
  if command -v wget >/dev/null 2>&1; then
    spin_run "Fetching uv (Python package installer)" \
      bash -c 'wget -qO- https://astral.sh/uv/install.sh | sh >/dev/null 2>&1'
    return
  fi
  fail "curl or wget is required to install uv."
}

print_logo

if command -v uv >/dev/null 2>&1; then
  ok "uv already installed ($(uv --version 2>/dev/null | awk '{print $2}'))"
else
  install_uv_quietly
  # uv installer drops the binary in ~/.local/bin or ~/.cargo/bin; expose it.
  for candidate in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    if [ -x "$candidate/uv" ] && [[ ":$PATH:" != *":$candidate:"* ]]; then
      export PATH="$candidate:$PATH"
    fi
  done
fi

if ! command -v uv >/dev/null 2>&1; then
  fail "uv not found after installation. Open a new shell and re-run."
fi

spin_run "Installing pythinker-code" \
  uv tool install --quiet --python 3.13 pythinker-code

printf '\n'
printf '  %s%spythinker%s is ready.\n'                       "$BOLD" "$FACE"  "$RESET"
printf '  %sRun%s %s%spythinker%s %sto start.%s\n\n'         "$DIM"  "$RESET" "$BOLD" "$IRIS" "$RESET" "$DIM" "$RESET"
