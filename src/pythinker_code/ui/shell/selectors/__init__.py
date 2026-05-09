"""Selector dialogs for Pythinker.

Each sub-module exposes one run_*() async function. Import from this package:

    from pythinker_code.ui.shell.selectors import run_theme_selector
"""

from pythinker_code.ui.shell.selectors.extension import run_extension_selector
from pythinker_code.ui.shell.selectors.oauth import (
    OAuthProviderEntry,
    OAuthProviderStatus,
    run_oauth_selector,
)
from pythinker_code.ui.shell.selectors.settings import (
    apply_settings_changes,
    run_settings_selector,
)
from pythinker_code.ui.shell.selectors.show_images import run_show_images_selector
from pythinker_code.ui.shell.selectors.theme import run_theme_selector
from pythinker_code.ui.shell.selectors.thinking import (
    LEVEL_DESCRIPTIONS,
    ThinkingLevel,
    run_thinking_selector,
)

__all__ = [
    "LEVEL_DESCRIPTIONS",
    "OAuthProviderEntry",
    "OAuthProviderStatus",
    "ThinkingLevel",
    "apply_settings_changes",
    "run_extension_selector",
    "run_oauth_selector",
    "run_settings_selector",
    "run_show_images_selector",
    "run_theme_selector",
    "run_thinking_selector",
]
