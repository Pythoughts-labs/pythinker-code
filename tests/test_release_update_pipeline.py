from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# Platform builders that create-or-update the GitHub Release on the tag push.
BUILDER_WORKFLOWS = (
    "windows-installer.yml",
    "linux-installer.yml",
    "release-pythinker-cli.yml",
)


def _step_block(workflow: str, name_fragment: str) -> str:
    """Return the YAML of the first step whose ``name:`` contains *name_fragment*,
    up to (but excluding) the next ``- name:`` step. Lets assertions target one
    step instead of the whole file, so an unrelated step can't satisfy or break
    them."""
    lines = workflow.splitlines()
    try:
        start = next(
            i
            for i, line in enumerate(lines)
            if line.lstrip().startswith("- name:") and name_fragment in line
        )
    except StopIteration:
        raise AssertionError(f"Step containing {name_fragment!r} not found in workflow") from None
    block = [lines[start]]
    for line in lines[start + 1 :]:
        if line.lstrip().startswith("- name:"):
            break
        block.append(line)
    return "\n".join(block)


def test_builders_create_release_as_prerelease() -> None:
    """Each builder must mark the Release prerelease.

    /releases/latest is date-based and ignores make_latest, so prerelease is
    the only flag that keeps an in-progress release (whichever builder wins the
    create race) out of the endpoint that install scripts and the in-app
    updater resolve. promote-release.yml clears it once every asset is present.
    """
    for name in BUILDER_WORKFLOWS:
        workflow = (WORKFLOWS / name).read_text()
        assert 'prerelease: "true"' in workflow, f"{name} must mark the release prerelease"


def test_release_is_promoted_only_after_update_assets_are_ready() -> None:
    promote_workflow = (WORKFLOWS / "promote-release.yml").read_text()

    # Runs on the tag push (not `release: published`, which a GITHUB_TOKEN
    # release never fires) so promotion always happens.
    assert "tags:" in promote_workflow

    # Promotion clears prerelease AND marks latest, and only after the wait.
    assert "-F prerelease=false" in promote_workflow
    assert "-f make_latest=true" in promote_workflow
    assert promote_workflow.index("Wait for install-channel readiness") < promote_workflow.index(
        "-F prerelease=false"
    )


def test_install_scripts_gate_on_asset_readiness() -> None:
    """The bootstrap installers must not 404 on a release caught mid-publish.

    install.ps1 resolves the newest release that actually carries the Windows
    installer + its .sha256 (skipping draft/prerelease), and install-native.sh
    waits for this version's archive + checksum before downloading.
    """
    ps1 = (ROOT / "scripts" / "install.ps1").read_text()
    assert "releases/latest" in ps1
    assert "releases?per_page=100" in ps1
    assert "Test-ReleaseHasInstaller" in ps1
    assert "Format-ReleaseApiError" in ps1
    assert "$release.prerelease" in ps1
    assert '"$exe.sha256"' in ps1

    sh = (ROOT / "scripts" / "install-native.sh").read_text()
    assert "release_has_assets" in sh
    assert "${tarball}.sha256" in sh

    # The three served copies must match their canonical source byte-for-byte.
    assert (ROOT / "docs" / "public" / "install.ps1").read_text() == ps1
    assert (ROOT / "web" / "public" / "install.ps1").read_text() == ps1
    assert (ROOT / "docs" / "public" / "install.sh").read_text() == sh
    assert (ROOT / "web" / "public" / "install.sh").read_text() == sh


def test_site_dispatch_uses_scoped_github_app_token_and_degrades_gracefully() -> None:
    workflow = (WORKFLOWS / "dispatch-pythinker-home-sync.yml").read_text()

    # Auth is the org-owned pythinker-release-bot App, never a personal PAT.
    assert "PYTHINKER_HOME_REPO_DISPATCH_TOKEN" not in workflow
    assert "PYTHINKER_RELEASE_BOT_APP_ID" in workflow
    assert "PYTHINKER_RELEASE_BOT_APP_PRIVATE_KEY" in workflow

    # The minted token is scoped to a single repo with contents-only write, and
    # the action is pinned by full commit SHA (not a floating tag) — supply chain.
    assert re.search(r"uses:\s*actions/create-github-app-token@[0-9a-f]{40}\b", workflow)
    assert "repositories: ${{ env.DISPATCH_REPO }}" in workflow
    assert "permission-contents: write" in workflow
    # The job's own GITHUB_TOKEN stays read-only; write is delegated to the
    # narrowly-scoped App token above.
    assert re.search(r"permissions:\s+contents:\s*read", workflow)

    # Best-effort and non-blocking: a missing/rotated App must never red-line
    # main. Scoped to the relevant steps so unrelated steps can't satisfy/break
    # them: the token step continues on error, and the dispatch step degrades
    # (exit 0) rather than failing loud — the daily pythinker-home cron is the
    # real sync guarantee.
    token_step = _step_block(workflow, "Mint GitHub App token")
    assert "continue-on-error: true" in token_step
    dispatch_step = _step_block(workflow, "Trigger pythinker-home sync")
    assert "exit 1" not in dispatch_step
    assert "exit 0" in dispatch_step

    # ...but degradation is SURFACED, not silently swallowed: a step-summary
    # warning plus a Slack alert keep a broken App visible.
    assert "::warning" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "SLACK_WEBHOOK_URL" in workflow
    assert "Non-blocking" in workflow


def test_windows_installer_signs_update_artifacts_when_credentials_are_available() -> None:
    installer_script = (ROOT / "packages" / "windows-installer" / "installer.iss").read_text()
    build_script = (ROOT / "packages" / "windows-installer" / "build.ps1").read_text()

    assert "CloseApplications=yes" in installer_script
    assert "CloseApplications=force" not in installer_script
    assert "SignTool=PythinkerSign" in installer_script
    assert "SignedUninstaller=yes" in installer_script
    assert re.search(r"NewPath\s*:=\s*Param\s*\+\s*';'\s*\+\s*OrigPath", installer_script)
    assert not re.search(r"NewPath\s*:=\s*OrigPath\s*\+\s*';'\s*\+\s*Param", installer_script)
    assert not re.search(r"StringChangeEx\(\s*OrigPath\s*,\s*Param\s*,", installer_script)

    # Signing only the final setup executable leaves Smart App Control and AV
    # heuristics to inspect unsigned bundled/native helper files. Keep signing
    # wired for the frozen executable, bundled DLL/PYD files, and Inno's
    # setup/uninstaller/temp copies.
    assert "@('.exe', '.dll', '.pyd')" in build_script
    assert "PYTHINKER_INNO_SIGN_SCRIPT" in build_script
    assert '-File `"$signScript`"' not in build_script
    assert "/SPythinkerSign=$signCommand" in build_script
    assert "/DUseInnoSignTool=1" in build_script


def test_release_asset_wait_covers_all_updater_channels() -> None:
    promote_workflow = (WORKFLOWS / "promote-release.yml").read_text()

    for expected_readiness_marker in (
        "PythinkerSetup-${version}.exe.sha256",
        "pythinker-code_${version}_amd64.deb.sha256",
        "pythinker-code_${version}_arm64.deb.sha256",
        "pythinker-code-${version}.x86_64.rpm.sha256",
        "pythinker-code-${version}.aarch64.rpm.sha256",
        "pythinker-${version}-x86_64-unknown-linux-gnu.tar.gz.sha256",
        "pythinker-${version}-aarch64-unknown-linux-gnu.tar.gz.sha256",
        "pythinker-${version}-aarch64-apple-darwin.tar.gz.sha256",
        "pythinker-${version}-x86_64-apple-darwin.tar.gz.sha256",
        "pythinker-${version}-x86_64-unknown-linux-gnu-onedir.tar.gz.sha256",
        "pythinker-${version}-aarch64-unknown-linux-gnu-onedir.tar.gz.sha256",
        "pythinker-${version}-aarch64-apple-darwin-onedir.tar.gz.sha256",
        "pythinker-${version}-x86_64-apple-darwin-onedir.tar.gz.sha256",
        "https://pypi.org/pypi/pythinker-code/${version}/json",
        "raw.githubusercontent.com/Pythoughts-labs/homebrew-pythinker",
        'version \\"${version}\\"',
    ):
        assert expected_readiness_marker in promote_workflow


def test_changelog_workflow_skips_release_prep_prs() -> None:
    """release.py opens `release/X.Y.Z` PRs titled `chore(release): prepare X.Y.Z`.

    changelog-entry-required.yml MUST skip its required check for that shape,
    or every release PR is blocked under branch protection. Assert both the
    title guard and the head-branch guard so neither half silently regresses.
    """
    wf = (WORKFLOWS / "changelog-entry-required.yml").read_text()
    # Title guard: chore(release)* → skip.
    assert '"chore(release)"*)' in wf, "missing chore(release) title skip"
    # Head-branch guard: release/* → skip.
    assert "release/*)" in wf, "missing release/* branch skip"
