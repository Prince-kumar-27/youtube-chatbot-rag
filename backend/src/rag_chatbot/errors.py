"""Turn raw AI-provider exceptions into messages a user can act on."""
from __future__ import annotations

from . import config

CONNECTION_ERRORS = {"APIConnectionError", "APITimeoutError", "ConnectError", "ConnectTimeout", "ReadTimeout"}


def explain_ai_error(exc: Exception) -> str:
    name = type(exc).__name__
    text = str(exc).lower()

    # ---- OpenAI ----
    if name == "AuthenticationError" or "incorrect api key" in text:
        return ("OpenAI rejected the API key (invalid or revoked). Create a new key, put it in "
                "backend/.env as OPENAI_API_KEY, and restart the backend.")
    if "insufficient_quota" in text or "exceeded your current quota" in text:
        return ("Your OpenAI account has no credit left. Add credit or billing at "
                "platform.openai.com, then try again.")

    # ---- Google Gemini ----
    if "api key not valid" in text or "api_key_invalid" in text:
        return ("Google rejected the API key. Check GOOGLE_API_KEY in backend/.env "
                "(no quotes or spaces), then restart the backend.")
    if "leaked" in text:
        return ("Google disabled this API key because it was exposed publicly. Create a new key at "
                "aistudio.google.com/apikey and keep it only in backend/.env.")
    if "resource_exhausted" in text or "quota exceeded" in text:
        return ("Gemini free-tier limit reached (too many requests per minute or per day). "
                "Wait a minute and try again, or set LLM_MODEL in backend/.env to another free model.")
    if "403" in text and "permission" in text:
        return ("Google denied access. Make sure the key is from aistudio.google.com/apikey and "
                "that the Gemini API is available in your country.")

    # ---- generic ----
    if name == "RateLimitError":
        return "The AI provider is rate-limiting requests. Wait a minute and try again."
    if name in {"NotFoundError", "PermissionDeniedError"} or (
        "model" in text and ("does not exist" in text or "do not have access" in text
                             or "is not found" in text or "not_found" in text)
    ):
        return (f"Your key cannot use the model '{config.LLM_MODEL}'. Set LLM_MODEL in "
                "backend/.env to a model you can use, then restart the backend.")
    if name in CONNECTION_ERRORS:
        return "Could not reach the AI provider. Check your internet connection, VPN or proxy settings."
    return f"The AI service failed ({name}). Check the backend terminal for details."