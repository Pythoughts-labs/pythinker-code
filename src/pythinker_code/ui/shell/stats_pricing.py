from __future__ import annotations

from pythinker_core.chat_provider import TokenUsage

# Prices in USD per million tokens.
# Source: Pi's models.generated.ts (blackbox/pi-main/packages/ai/src/models.generated.ts)
# Format: {model_id: (input, output, cache_read, cache_write)}
_PRICE_TABLE: dict[str, tuple[float, float, float, float]] = {
    # Anthropic — direct API
    "claude-3-haiku-20240307":       (0.25,  1.25,  0.03,   0.3),
    "claude-3-sonnet-20240229":      (3.0,   15.0,  0.3,    0.3),
    "claude-3-opus-20240229":        (15.0,  75.0,  1.5,    18.75),
    "claude-3-5-haiku-20241022":     (0.8,   4.0,   0.08,   1.0),
    "claude-3-5-haiku-latest":       (0.8,   4.0,   0.08,   1.0),
    "claude-3-5-sonnet-20240620":    (3.0,   15.0,  0.3,    3.75),
    "claude-3-5-sonnet-20241022":    (3.0,   15.0,  0.3,    3.75),
    "claude-3-7-sonnet-20250219":    (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4-20250514":      (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4-0":             (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4":               (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4-5":             (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4-5-20250929":    (3.0,   15.0,  0.3,    3.75),
    "claude-sonnet-4-6":             (3.0,   15.0,  0.3,    3.75),
    "claude-opus-4-20250514":        (15.0,  75.0,  1.5,    18.75),
    "claude-opus-4-0":               (15.0,  75.0,  1.5,    18.75),
    "claude-opus-4-1":               (15.0,  75.0,  1.5,    18.75),
    "claude-opus-4-1-20250805":      (15.0,  75.0,  1.5,    18.75),
    "claude-opus-4-5":               (5.0,   25.0,  0.5,    6.25),
    "claude-opus-4-5-20251101":      (5.0,   25.0,  0.5,    6.25),
    "claude-haiku-4-5":              (1.0,   5.0,   0.1,    1.25),
    "claude-haiku-4-5-20251001":     (1.0,   5.0,   0.1,    1.25),
    # OpenAI GPT-5 family
    "gpt-5":                         (2.5,   15.0,  0.25,   0.0),
    "gpt-5.5":                       (2.5,   15.0,  0.25,   0.0),
    "gpt-5-chat-latest":             (2.5,   15.0,  0.25,   0.0),
    "gpt-5-mini":                    (0.75,  4.5,   0.075,  0.0),
    "gpt-5.4-mini":                  (0.75,  4.5,   0.075,  0.0),
    "gpt-5-nano":                    (0.75,  4.5,   0.075,  0.0),
    "gpt-5-pro":                     (5.0,   30.0,  0.5,    0.0),
    "gpt-5.5-pro":                   (5.0,   30.0,  0.5,    0.0),
    "gpt-4o":                        (2.5,   10.0,  0.25,   0.0),
    "gpt-4o-mini":                   (0.15,  0.6,   0.075,  0.0),
    # DeepSeek (via opencode-go or direct)
    "deepseek-v4-flash":             (0.14,  0.28,  0.0028, 0.0),
    "deepseek-v4-pro":               (0.435, 0.87,  0.003625, 0.0),
    "deepseek-chat":                 (0.27,  1.1,   0.0,    0.0),
    "deepseek-reasoner":             (0.55,  2.19,  0.55,   0.0),
    # GLM (Z.AI / OpenCode-Go)
    "glm-5":                         (1.0,   3.2,   0.2,    0.0),
    "glm-5.1":                       (1.4,   4.4,   0.26,   0.0),
    "glm-5-turbo":                   (0.5,   1.5,   0.1,    0.0),
    "glm-4.7":                       (0.5,   1.5,   0.1,    0.0),
    "glm-4.5-air":                   (0.3,   1.0,   0.06,   0.0),
    # Kimi (opencode-go)
    "kimi-k2.5":                     (0.6,   3.0,   0.08,   0.0),
    "kimi-k2.6":                     (0.95,  4.0,   0.16,   0.0),
    # MiniMax (opencode-go / anthropic shape)
    "minimax-m2.5":                  (0.3,   1.2,   0.06,   0.0),
    "minimax-m2.7":                  (0.3,   1.2,   0.06,   0.0),
    # Gemini (Google)
    "gemini-2.0-flash":              (0.1,   0.4,   0.025,  0.0),
    "gemini-2.0-flash-lite":         (0.075, 0.3,   0.0,    0.0),
    "gemini-2.5-flash":              (0.3,   2.5,   0.03,   0.0),
    "gemini-2.5-flash-lite":         (0.1,   0.4,   0.01,   0.0),
    "gemini-2.5-pro":                (1.25,  10.0,  0.125,  0.0),
}


def get_cost_usd(model: str, usage: TokenUsage) -> float:
    """Return estimated USD cost for one LLM step.

    Looks up the exact model ID first; falls back to prefix matching
    for versioned aliases (e.g. ``claude-sonnet-4-5-20250929`` →
    ``claude-sonnet-4-5``). Returns 0.0 for unknown models.
    """
    pricing = _PRICE_TABLE.get(model)
    if pricing is None:
        # Prefix fallback: longest matching key wins.
        best: tuple[float, float, float, float] | None = None
        best_len = 0
        for key, val in _PRICE_TABLE.items():
            if model.startswith(key) and len(key) > best_len:
                best = val
                best_len = len(key)
        if best is None:
            return 0.0
        pricing = best

    inp, out, cr, cw = pricing
    total = (
        usage.input_other * inp
        + usage.output * out
        + usage.input_cache_read * cr
        + usage.input_cache_creation * cw
    ) / 1_000_000
    return total
