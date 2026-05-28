from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_release_is_marked_latest_only_after_update_assets_are_ready() -> None:
    release_workflow = (ROOT / ".github" / "workflows" / "release-pythinker-cli.yml").read_text()
    dispatch_workflow = (
        ROOT / ".github" / "workflows" / "dispatch-pythinker-home-sync.yml"
    ).read_text()

    assert 'make_latest: "false"' in release_workflow
    assert "Mark release latest after assets are ready" in dispatch_workflow
    assert "-f make_latest=true" in dispatch_workflow
    assert dispatch_workflow.index("Wait for all release assets") < dispatch_workflow.index(
        "Mark release latest after assets are ready"
    )


def test_release_asset_wait_covers_all_updater_channels() -> None:
    dispatch_workflow = (
        ROOT / ".github" / "workflows" / "dispatch-pythinker-home-sync.yml"
    ).read_text()

    for expected_asset_fragment in (
        "PythinkerSetup-",
        "_amd64.deb",
        "_arm64.deb",
        ".x86_64.rpm",
        ".aarch64.rpm",
        "x86_64-unknown-linux-gnu.tar.gz",
        "aarch64-unknown-linux-gnu.tar.gz",
        "aarch64-apple-darwin.tar.gz",
        "x86_64-apple-darwin.tar.gz",
    ):
        assert expected_asset_fragment in dispatch_workflow
