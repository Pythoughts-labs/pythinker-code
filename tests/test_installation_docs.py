import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    return project["project"]["version"]


def test_unix_readme_installer_uses_canonical_native_endpoint() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "curl -fsSL https://pythinker.com/install.sh | bash" in readme
    assert "scripts/install.sh | bash" not in readme
    assert "scripts/install.sh | sh" not in readme


def test_windows_readme_documents_powershell_one_liner() -> None:
    readme = (ROOT / "README.md").read_text()

    assert (
        'powershell -c "irm https://raw.githubusercontent.com/mohamed-elkholy95/'
        'Pythinker-Code/main/scripts/install.ps1 | iex"'
    ) in readme
    assert "-File $installer" not in readme


def test_getting_started_uses_canonical_native_installer_url() -> None:
    guide = (ROOT / "docs" / "en" / "guides" / "getting-started.md").read_text()

    assert "https://code.pythinker.com/install.sh" not in guide
    assert "https://code.pythinker.com/install.ps1" not in guide
    assert "curl -fsSL https://pythinker.com/install.sh | bash" in guide
    assert (
        "https://raw.githubusercontent.com/mohamed-elkholy95/"
        "Pythinker-Code/main/scripts/install.ps1"
    ) in guide


def test_windows_installer_runs_uv_bootstrap_in_current_process() -> None:
    installer = (ROOT / "scripts" / "install.ps1").read_text()

    # Bootstrapping uv must happen in the current process (dot-source) so its
    # PATH / registry side effects survive. A `powershell -File` subprocess
    # would discard them.
    assert "-File $uvInstaller" not in installer
    assert ". $uvInstaller" in installer
    assert "winget install --id astral-sh.uv" in installer


def test_readme_downloads_rpm_before_local_install() -> None:
    readme = (ROOT / "README.md").read_text()
    version = project_version()

    rpm = f"pythinker-code-{version}.x86_64.rpm"
    checksum = f"{rpm}.sha256"
    release_url = (
        f"https://github.com/mohamed-elkholy95/Pythinker-Code/releases/download/v{version}"
    )

    assert f"curl -LO {release_url}/{rpm}" in readme
    assert f"curl -LO {release_url}/{checksum}" in readme
    assert f"sha256sum -c {checksum}" in readme
    rpm_block = readme[readme.index(f"curl -LO {release_url}/{rpm}") :]
    assert rpm_block.index(f"curl -LO {release_url}/{rpm}") < rpm_block.index(
        f"sudo dnf install ./{rpm}"
    )


def test_quick_start_names_open_suse_installer_and_install_sh_is_native_shim() -> None:
    readme = (ROOT / "README.md").read_text()
    installer = (ROOT / "scripts" / "install.sh").read_text()
    version = project_version()
    rpm = f"pythinker-code-{version}.x86_64.rpm"

    assert f"Linux (Fedora / RHEL)** | Download `{rpm}`, then `sudo dnf install ./{rpm}`" in readme
    assert f"Linux (openSUSE)** | Download `{rpm}`, then `sudo zypper install ./{rpm}`" in readme
    assert "install-native.sh" in installer
    assert "https://pythinker.com/install.sh" in installer


def test_public_install_script_matches_native_source_of_truth() -> None:
    native = (ROOT / "scripts" / "install-native.sh").read_bytes()

    assert (ROOT / "docs" / "public" / "install.sh").read_bytes() == native
    assert (ROOT / "web" / "public" / "install.sh").read_bytes() == native

    expected_headers = (
        "/install.sh\n"
        "  Content-Type: text/x-shellscript; charset=utf-8\n"
        "  Cache-Control: public, max-age=300, s-maxage=900, stale-if-error=86400\n"
    )
    assert expected_headers in (ROOT / "docs" / "public" / "_headers").read_text()
    assert expected_headers in (ROOT / "web" / "public" / "_headers").read_text()


def test_installation_docs_do_not_use_placeholder_package_artifacts() -> None:
    docs = [
        ROOT / "README.md",
        ROOT / "packages" / "linux-installer" / "README.md",
    ]

    for doc in docs:
        text = doc.read_text()
        assert "releases/download/vx.y.z" not in text
        assert "pythinker-code-x.y.z" not in text
        assert "pythinker-code_x.y.z" not in text


def test_readme_references_existing_terminal_demo_asset() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "docs/media/pythinker-code.gif" not in readme
    assert "docs/media/pythinker-cli.gif" in readme
    assert (ROOT / "docs" / "media" / "pythinker-cli.gif").exists()
