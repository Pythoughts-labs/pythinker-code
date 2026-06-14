from __future__ import annotations

from pythinker_core.chat_provider import TokenUsage

# Prices in USD per million tokens.
# Pricing snapshot from a public multi-provider model catalog; refresh manually when prices change.
# Format: {model_id: (input, output, cache_read, cache_write)}
_PRICE_TABLE: dict[str, tuple[float, float, float, float]] = {
    # Anthropic — direct API
    "claude-3-haiku-20240307": (0.25, 1.25, 0.03, 0.3),
    "claude-3-sonnet-20240229": (3.0, 15.0, 0.3, 0.3),
    "claude-3-opus-20240229": (15.0, 75.0, 1.5, 18.75),
    "claude-3-5-haiku-20241022": (0.8, 4.0, 0.08, 1.0),
    "claude-3-5-haiku-latest": (0.8, 4.0, 0.08, 1.0),
    "claude-3-5-sonnet-20240620": (3.0, 15.0, 0.3, 3.75),
    "claude-3-5-sonnet-20241022": (3.0, 15.0, 0.3, 3.75),
    "claude-3-7-sonnet-20250219": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4-20250514": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4-0": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4-5": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4-5-20250929": (3.0, 15.0, 0.3, 3.75),
    "claude-sonnet-4-6": (3.0, 15.0, 0.3, 3.75),
    "claude-opus-4-20250514": (15.0, 75.0, 1.5, 18.75),
    "claude-opus-4-0": (15.0, 75.0, 1.5, 18.75),
    "claude-opus-4-1": (15.0, 75.0, 1.5, 18.75),
    "claude-opus-4-1-20250805": (15.0, 75.0, 1.5, 18.75),
    "claude-opus-4-5": (5.0, 25.0, 0.5, 6.25),
    "claude-opus-4-5-20251101": (5.0, 25.0, 0.5, 6.25),
    "claude-haiku-4-5": (1.0, 5.0, 0.1, 1.25),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.1, 1.25),
    # OpenAI GPT-5 family
    "gpt-5": (2.5, 15.0, 0.25, 0.0),
    "gpt-5.5": (2.5, 15.0, 0.25, 0.0),
    "gpt-5-chat-latest": (2.5, 15.0, 0.25, 0.0),
    "gpt-5-mini": (0.75, 4.5, 0.075, 0.0),
    "gpt-5.4-mini": (0.75, 4.5, 0.075, 0.0),
    "gpt-5-nano": (0.75, 4.5, 0.075, 0.0),
    "gpt-5-pro": (5.0, 30.0, 0.5, 0.0),
    "gpt-5.5-pro": (5.0, 30.0, 0.5, 0.0),
    "gpt-4o": (2.5, 10.0, 0.25, 0.0),
    "gpt-4o-mini": (0.15, 0.6, 0.075, 0.0),
    # DeepSeek (via opencode-go or direct)
    "deepseek-v4-flash": (0.14, 0.28, 0.0028, 0.0),
    "deepseek-v4-pro": (0.435, 0.87, 0.003625, 0.0),
    "deepseek-chat": (0.27, 1.1, 0.0, 0.0),
    "deepseek-reasoner": (0.55, 2.19, 0.55, 0.0),
    # GLM (Z.AI / OpenCode-Go)
    "glm-5": (1.0, 3.2, 0.2, 0.0),
    # GLM-5.2 list pricing is not yet published; estimate at the GLM-5.1 flagship
    # tier (offline fallback only — models.dev overrides when available).
    "glm-5.2": (1.4, 4.4, 0.26, 0.0),
    "glm-5.1": (1.4, 4.4, 0.26, 0.0),
    "glm-5-turbo": (0.5, 1.5, 0.1, 0.0),
    "glm-4.7": (0.5, 1.5, 0.1, 0.0),
    "glm-4.5-air": (0.3, 1.0, 0.06, 0.0),
    # Moonshot K2 (opencode-go / Moonshot / Kimi coding plan)
    "kimi-k2.5": (0.6, 3.0, 0.08, 0.0),
    "kimi-k2.6": (0.95, 4.0, 0.16, 0.0),
    "kimi-k2.7-code": (0.95, 4.0, 0.19, 0.0),
    # MiniMax (opencode-go / anthropic shape)
    "minimax-m2.5": (0.3, 1.2, 0.06, 0.0),
    "minimax-m2.7": (0.3, 1.2, 0.06, 0.0),
    # Gemini (Google)
    "gemini-2.0-flash": (0.1, 0.4, 0.025, 0.0),
    "gemini-2.0-flash-lite": (0.075, 0.3, 0.0, 0.0),
    "gemini-2.5-flash": (0.3, 2.5, 0.03, 0.0),
    "gemini-2.5-flash-lite": (0.1, 0.4, 0.01, 0.0),
    "gemini-2.5-pro": (1.25, 10.0, 0.125, 0.0),
}


def get_cost_usd(model: str, usage: TokenUsage) -> float:
    """Return estimated USD cost for one LLM step.

    Resolution order:
    1. Exact match in models.dev catalog (load_catalog)
    2. Longest prefix match in catalog
    3. Exact match in hardcoded _PRICE_TABLE (offline/unknown-model fallback)
    4. Longest prefix match in _PRICE_TABLE
    5. 0.0
    """
    from pythinker_code.models_dev import ModelPrice, load_catalog

    def _apply(p: tuple[float, float, float, float] | ModelPrice) -> float:
        if isinstance(p, ModelPrice):
            inp, out, cr, cw = p.input, p.output, p.cache_read, p.cache_write
        else:
            inp, out, cr, cw = p
        return (
            usage.input_other * inp
            + usage.output * out
            + usage.input_cache_read * cr
            + usage.input_cache_creation * cw
        ) / 1_000_000

    catalog = load_catalog()

    # 1. Catalog exact
    if model in catalog:
        return _apply(catalog[model])

    # 2. Catalog prefix (longest wins)
    best_cat: ModelPrice | None = None
    best_cat_len = 0
    for key, val in catalog.items():
        if model.startswith(key) and len(key) > best_cat_len:
            best_cat = val
            best_cat_len = len(key)
    if best_cat is not None:
        return _apply(best_cat)

    # 3. Hardcoded exact
    if model in _PRICE_TABLE:
        return _apply(_PRICE_TABLE[model])

    # 4. Hardcoded prefix (longest wins)
    best: tuple[float, float, float, float] | None = None
    best_len = 0
    for key, val in _PRICE_TABLE.items():
        if model.startswith(key) and len(key) > best_len:
            best = val
            best_len = len(key)
    if best is not None:
        return _apply(best)

    return 0.0
