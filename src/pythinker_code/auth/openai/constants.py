"""OAuth constants for the OpenAI login flows: URLs, client id, and callback ports."""

from __future__ import annotations

OPENAI_API_BASE_URL = "https://api.openai.com/v1"
OPENAI_CHATGPT_BASE_URL = "https://chatgpt.com/backend-api/codex"
OPENAI_CHATGPT_MODELS_URL = f"{OPENAI_CHATGPT_BASE_URL}/models?client_version=1.0.0"
OPENAI_AUTH_ISSUER = "https://auth.openai.com"
OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_BROWSER_PORT = 1455
OPENAI_BROWSER_FALLBACK_PORT = 1457
OPENAI_BROWSER_REDIRECT_PATH = "/auth/callback"
OPENAI_DEVICE_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"
OPENAI_DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
OPENAI_CHATGPT_OAUTH_KEY = "oauth/openai-chatgpt"
