from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "packages" / "homebrew-tap" / "generate-formula.py"
TEMPLATE = ROOT / "packages" / "homebrew-tap" / "pythinker-code.rb.tmpl"


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("homebrew_generate_formula", GENERATOR)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_native_homebrew_formula_renders_release_tarballs() -> None:
    generator = load_generator()
    version = "1.2.3"
    assets = {}
    for target in generator.NATIVE_TARGETS:
        name = target.asset_name(version)
        assets[name] = {
            "browser_download_url": f"https://example.invalid/{name}",
            "digest": "sha256:" + ("a" * 64),
        }

    formula = generator.render_formula(
        TEMPLATE.read_text(encoding="utf-8"), generator.native_replacements(version, assets)
    )

    assert "include Language::Python::Virtualenv" not in formula
    assert 'version "1.2.3"' in formula
    assert "pythinker-1.2.3-aarch64-apple-darwin-onedir.tar.gz" in formula
    assert "pythinker-1.2.3-x86_64-apple-darwin-onedir.tar.gz" in formula
    assert "pythinker-1.2.3-aarch64-unknown-linux-gnu-onedir.tar.gz" in formula
    assert "pythinker-1.2.3-x86_64-unknown-linux-gnu-onedir.tar.gz" in formula
    assert "on_macos do" in formula
    assert "on_linux do" in formula
    assert "on_arm do" in formula
    assert "on_intel do" in formula
    assert 'libexec.install Dir["*"]' in formula
    assert '(libexec/".pythinker-native").write "pythinker-native-build\\n"' in formula
    assert 'bin.write_exec_script libexec/"pythinker"' in formula


def test_native_homebrew_formula_fails_when_asset_missing() -> None:
    generator = load_generator()

    try:
        generator.native_replacements("1.2.3", {})
    except RuntimeError as exc:
        assert "release asset missing" in str(exc)
    else:
        raise AssertionError("expected missing native asset to fail formula generation")


def test_native_homebrew_formula_caveats_show_logo() -> None:
    generator = load_generator()
    version = "1.2.3"
    assets = {}
    for target in generator.NATIVE_TARGETS:
        name = target.asset_name(version)
        assets[name] = {
            "browser_download_url": f"https://example.invalid/{name}",
            "digest": "sha256:" + ("a" * 64),
        }

    formula = generator.render_formula(
        TEMPLATE.read_text(encoding="utf-8"), generator.native_replacements(version, assets)
    )

    # Homebrew prints `caveats` after install — this is where the static robot
    # logo (parity with install.sh / install.ps1) must live.
    assert "def caveats" in formula
    assert "pythinker code · your next CLI agent" in formula
    # The robot-head mouth row is the most distinctive line of the art.
    assert "▙▄▄▄≡▄▄▄▟" in formula
