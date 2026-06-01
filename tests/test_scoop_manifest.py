from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "packages" / "scoop-bucket" / "generate-manifest.py"
TEMPLATE = ROOT / "packages" / "scoop-bucket" / "pythinker-code.json.tmpl"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scoop_generate_manifest", GENERATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _fake_assets(generator: ModuleType, version: str) -> dict[str, dict[str, str]]:
    name = generator.windows_zip_asset_name(version)
    return {
        name: {
            "browser_download_url": f"https://example.invalid/{name}",
            "digest": "sha256:" + ("a" * 64),
        }
    }


def test_scoop_manifest_renders_windows_zip() -> None:
    generator = load_generator()
    version = "1.2.3"
    assets = _fake_assets(generator, version)

    manifest_text = generator.render_manifest(
        TEMPLATE.read_text(encoding="utf-8"), generator.manifest_replacements(version, assets)
    )
    manifest = json.loads(manifest_text)

    assert manifest["version"] == "1.2.3"
    assert (
        manifest["architecture"]["64bit"]["url"]
        == "https://example.invalid/pythinker-1.2.3-x86_64-pc-windows-msvc-onedir.zip"
    )
    assert manifest["architecture"]["64bit"]["hash"] == "a" * 64
    assert manifest["bin"] == "pythinker\\pythinker.exe"
    assert manifest["env_set"]["PYTHINKER_MANAGED"] == "scoop"


def test_scoop_manifest_fails_when_asset_missing() -> None:
    generator = load_generator()
    with pytest.raises(RuntimeError, match="release asset missing"):
        generator.manifest_replacements("1.2.3", {})


def test_windows_zip_asset_name_matches_release_workflow() -> None:
    generator = load_generator()
    # Exact shape produced by release-pythinker-cli.yml's onedir packaging step.
    assert (
        generator.windows_zip_asset_name("0.27.0")
        == "pythinker-0.27.0-x86_64-pc-windows-msvc-onedir.zip"
    )
