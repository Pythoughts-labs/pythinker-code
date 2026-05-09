from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_unix_readme_installer_invokes_bash_for_bash_script() -> None:
    readme = (ROOT / "README.md").read_text()

    assert "scripts/install.sh | bash" in readme
    assert "scripts/install.sh | sh" not in readme


def test_windows_readme_avoids_remote_invoke_expression() -> None:
    readme = (ROOT / "README.md").read_text()

    # Remote `iex` is what AV scanners flag — keep using a downloaded file.
    assert "scripts/install.ps1 | iex" not in readme
    # The installer must run in the user's *current* shell so PATH updates from
    # uv are immediately visible. Spawning a child via `powershell -File`
    # would leave the parent shell without uv/pythinker on PATH.
    assert "& $installer" in readme
    assert "-File $installer" not in readme


def test_windows_installer_runs_uv_bootstrap_in_current_process() -> None:
    installer = (ROOT / "scripts" / "install.ps1").read_text()

    # Bootstrapping uv must happen in the current process (dot-source) so its
    # PATH / registry side effects survive. A `powershell -File` subprocess
    # would discard them.
    assert "-File $uvInstaller" not in installer
    assert ". $uvInstaller" in installer
    assert "winget install --id astral-sh.uv" in installer
