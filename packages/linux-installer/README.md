# Pythinker Linux Native Packages

Builds `.deb` (Debian / Ubuntu) and `.rpm` (Fedora / RHEL / openSUSE) packages
for Pythinker Code by freezing the CLI with PyInstaller and wrapping the
output with [`fpm`](https://github.com/jordansissel/fpm).

End-user install once an artifact is downloaded from the GitHub Release:

```sh
# Debian / Ubuntu
sudo dpkg -i pythinker-code_x.y.z_amd64.deb
sudo apt-get install -f       # only needed if dependencies fail to resolve

# Fedora / RHEL / openSUSE
sudo rpm -i pythinker-code-x.y.z.x86_64.rpm
# or
sudo dnf install ./pythinker-code-x.y.z.x86_64.rpm
```

The package drops a single executable at `/usr/bin/pythinker` and a license
file at `/usr/share/doc/pythinker-code/LICENSE`.

## Prerequisites (local builds)

- Linux x86_64 host (use `arch=arm64` on Apple Silicon under Docker for
  aarch64 builds — CI handles this with QEMU).
- Python 3.13 + a venv with `pyinstaller` available
- Ruby (for `fpm`) — `sudo apt-get install -y ruby ruby-dev` then `sudo gem install fpm`

## Build

```sh
bash packages/linux-installer/build.sh 0.13.0
```

Outputs to `dist/`:

- `pythinker-code_0.13.0_amd64.deb`
- `pythinker-code-0.13.0.x86_64.rpm`
- `pythinker-code-0.13.0-linux-x86_64.tar.gz` (used by `scripts/install-native.sh`)

## CI

`.github/workflows/linux-installer.yml` runs this build on every
`v[0-9]+.[0-9]+.[0-9]+` tag (matrix: x86_64 + aarch64) and uploads every
artifact to the corresponding GitHub Release.
