"""Static fallback model catalogs for the OpenAI ChatGPT and API platforms."""

from __future__ import annotations

from pythinker_code.auth.platforms import ModelInfo

OPENAI_CHATGPT_FALLBACK_MODELS = [
    ModelInfo(
        id="gpt-5.5",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.5",
    ),
    ModelInfo(
        id="gpt-5.4",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.4",
    ),
    ModelInfo(
        id="gpt-5.4-mini",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.4 Mini",
    ),
    ModelInfo(
        id="gpt-5.3-codex",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.3 Codex",
    ),
    ModelInfo(
        id="gpt-5.3-codex-spark",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.3 Codex Spark",
    ),
    ModelInfo(
        id="gpt-5.2",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.2",
    ),
]

OPENAI_API_FALLBACK_MODELS = [
    *OPENAI_CHATGPT_FALLBACK_MODELS,
    ModelInfo(
        id="gpt-5.4-nano",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.4 Nano",
    ),
    ModelInfo(
        id="gpt-5.1",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5.1",
    ),
    ModelInfo(
        id="gpt-5",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5",
    ),
    ModelInfo(
        id="gpt-5-codex",
        context_length=400000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-5 Codex",
    ),
    ModelInfo(
        id="gpt-4.1",
        context_length=1047576,
        supports_reasoning=False,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-4.1",
    ),
    ModelInfo(
        id="gpt-4.1-mini",
        context_length=1047576,
        supports_reasoning=False,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-4.1 Mini",
    ),
    ModelInfo(
        id="gpt-4.1-nano",
        context_length=1047576,
        supports_reasoning=False,
        supports_image_in=True,
        supports_video_in=False,
        display_name="GPT-4.1 Nano",
    ),
    ModelInfo(
        id="o3",
        context_length=200000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="o3",
    ),
    ModelInfo(
        id="o4-mini",
        context_length=200000,
        supports_reasoning=True,
        supports_image_in=True,
        supports_video_in=False,
        display_name="o4-mini",
    ),
]
