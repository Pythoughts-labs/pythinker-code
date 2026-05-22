#!/usr/bin/env bash
# Pythinker Code — native curl-bash installer.
#
# Downloads a PyInstaller-built tarball for your OS + arch from the latest
# GitHub Release, verifies its SHA-256, installs it under
#   ~/.local/share/pythinker     (the frozen binary + its _internal/ tree)
# and symlinks
#   ~/.local/bin/pythinker       (so the CLI is on PATH out of the box).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/mohamed-elkholy95/Pythinker-Code/main/scripts/install-native.sh | bash
#
#   # Pin a specific version:
#   curl -fsSL .../install-native.sh | bash -s -- --version 0.13.0
#
#   # Or run locally:
#   bash scripts/install-native.sh --version 0.13.0
#
# Supported targets:
#   linux-x86_64, linux-aarch64
#   macos-arm64 (Apple Silicon), macos-x86_64 (Intel)
#
# Windows users: use the native PythinkerSetup-x.y.z.exe installer instead.
set -euo pipefail

# --- args -----------------------------------------------------------------
VERSION=""
INSTALL_PREFIX="${PYTHINKER_INSTALL_PREFIX:-$HOME/.local}"
NO_COLOR="${NO_COLOR:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    --prefix)  INSTALL_PREFIX="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,/^set -euo/p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

REPO="mohamed-elkholy95/Pythinker-Code"

# --- color ---------------------------------------------------------------
if [ -t 1 ] && [ -z "$NO_COLOR" ] && [ "${TERM:-}" != "dumb" ]; then
  IRIS=$'\033[38;5;152m'; CORAL=$'\033[38;5;216m'; DIM=$'\033[2m'
  BOLD=$'\033[1m'; RESET=$'\033[0m'
else
  IRIS=""; CORAL=""; DIM=""; BOLD=""; RESET=""
fi
step() { printf '  %s⠿%s %s\n' "$IRIS" "$RESET" "$1"; }
ok()   { printf '  %s✓%s %s\n' "$IRIS" "$RESET" "$1"; }
fail() { printf '  %s✗%s %s\n' "$CORAL" "$RESET" "$1" >&2; exit 1; }

# --- detect target -------------------------------------------------------
os="$(uname -s)"
arch="$(uname -m)"
case "$os" in
  Linux)  os_slug="linux"  ;;
  Darwin) os_slug="macos"  ;;
  MINGW*|MSYS*|CYGWIN*)
    fail "On Windows, use the native PythinkerSetup-x.y.z.exe installer instead." ;;
  *) fail "unsupported OS: $os" ;;
esac
case "$arch" in
  x86_64|amd64)
    arch_slug="x86_64" ;;
  aarch64|arm64)
    # Linux reports aarch64; macOS reports arm64. Tarball naming follows
    # the convention each OS expects in its tarball filenames.
    if [ "$os_slug" = "macos" ]; then arch_slug="arm64"; else arch_slug="aarch64"; fi ;;
  *) fail "unsupported arch: $arch" ;;
esac
target="${os_slug}-${arch_slug}"

# --- resolve version -----------------------------------------------------
if [ -z "$VERSION" ]; then
  step "Looking up latest Pythinker release"
  api="https://api.github.com/repos/${REPO}/releases/latest"
  # We avoid jq to keep the installer dependency-free.
  if command -v curl >/dev/null 2>&1; then
    payload="$(curl -fsSL "$api")"
  elif command -v wget >/dev/null 2>&1; then
    payload="$(wget -qO- "$api")"
  else
    fail "need curl or wget to fetch the release index"
  fi
  VERSION="$(printf '%s' "$payload" | sed -nE 's/.*"tag_name": *"v([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' | head -n 1)"
  if [ -z "$VERSION" ]; then
    fail "could not parse latest release tag from $api"
  fi
  ok "Latest version is $VERSION"
fi

tarball="pythinker-code-${VERSION}-${target}.tar.gz"
tarball_url="https://github.com/${REPO}/releases/download/v${VERSION}/${tarball}"
sha_url="${tarball_url}.sha256"

# --- download + verify --------------------------------------------------
tmpdir="$(mktemp -d -t pythinker-install.XXXXXX)"
trap 'rm -rf "$tmpdir"' EXIT
step "Downloading $tarball"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$tarball_url" -o "$tmpdir/$tarball" || fail "download failed: $tarball_url"
  curl -fsSL "$sha_url"     -o "$tmpdir/$tarball.sha256" || fail "sha256 missing: $sha_url"
else
  wget -q "$tarball_url" -O "$tmpdir/$tarball" || fail "download failed"
  wget -q "$sha_url"     -O "$tmpdir/$tarball.sha256" || fail "sha256 missing"
fi

step "Verifying SHA-256"
expected="$(awk '{print $1}' "$tmpdir/$tarball.sha256")"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$tmpdir/$tarball" | awk '{print $1}')"
elif command -v shasum >/dev/null 2>&1; then
  actual="$(shasum -a 256 "$tmpdir/$tarball" | awk '{print $1}')"
else
  fail "need sha256sum or shasum to verify the download"
fi
if [ "$expected" != "$actual" ]; then
  fail "SHA-256 mismatch: expected $expected, got $actual"
fi
ok "Checksum OK"

# --- install -----------------------------------------------------------
share_dir="$INSTALL_PREFIX/share/pythinker"
bin_dir="$INSTALL_PREFIX/bin"

step "Installing into $share_dir"
rm -rf "$share_dir"
mkdir -p "$share_dir" "$bin_dir"
tar -C "$share_dir" --strip-components=1 -xzf "$tmpdir/$tarball"

ln -sfn "$share_dir/pythinker" "$bin_dir/pythinker"
ok "Installed $(${bin_dir}/pythinker --version 2>/dev/null || echo "pythinker $VERSION")"

# --- PATH guidance --------------------------------------------------------
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *)
    printf '\n  %sNote:%s %s is not on your PATH.\n' "$BOLD" "$RESET" "$bin_dir"
    printf '  Add this to your shell profile (~/.bashrc, ~/.zshrc, ~/.config/fish/config.fish):\n'
    printf '\n    %sexport PATH="%s:$PATH"%s\n\n' "$DIM" "$bin_dir" "$RESET"
    ;;
esac

printf '\n  %s%spythinker%s is ready. Run %s%spythinker%s to start.\n\n' \
  "$BOLD" "$IRIS" "$RESET" "$BOLD" "$IRIS" "$RESET"
