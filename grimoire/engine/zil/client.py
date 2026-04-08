"""OpenAI-compatible client factory and pipeline call helpers for ZIL⌀.

get_client()       — returns the right OpenAI client for the active provider
structured_parse() — wraps beta.parse() with Ollama compatibility fixes
tool_create()      — wraps chat.completions.create() with the same fixes

Ollama compatibility handled here:
  - max_tokens set to cfg.effective_max_tokens (default 8192) to prevent truncation
  - num_ctx set via extra_body so input + output fit in the context window
  - Qwen3 thinking disabled via /no_think in the system message (saves ~30% of tokens)
"""

from __future__ import annotations

from typing import Any, Type

from openai import OpenAI
from pydantic import BaseModel


def get_client() -> OpenAI:
    """Return a configured OpenAI-compatible client for the active provider."""
    from zil.config import get_config
    cfg = get_config()

    if cfg.provider == "ollama":
        return OpenAI(
            api_key="ollama",  # Ollama ignores the key; any non-empty string works
            base_url=cfg.ollama_base_url,
        )

    # OpenAI (default)
    if not cfg.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file, or switch to a local model with "
            "'zil chat --model ollama:<model-name>'."
        )
    return OpenAI(api_key=cfg.openai_api_key)


def _build_extra_body() -> dict | None:
    """Build Ollama-specific extra_body options, or None for OpenAI."""
    from zil.config import get_config
    cfg = get_config()
    if cfg.provider != "ollama":
        return None
    extra: dict[str, Any] = {"options": {"num_ctx": cfg.ollama_num_ctx}}
    # Disable Qwen3 chain-of-thought thinking — it burns output tokens
    # before the actual response is written, causing truncation.
    if "qwen3" in cfg.model.lower():
        extra["think"] = False
    return extra


def _patch_system_nothink(messages: list[dict]) -> list[dict]:
    """For Qwen3 on Ollama, prepend /no_think to the system message.

    This is a belt-and-suspenders approach alongside think=False in extra_body.
    Qwen3 respects /no_think as a special token anywhere in the system prompt.
    Returns a shallow-patched copy; does not mutate the original list.
    """
    from zil.config import get_config
    cfg = get_config()
    if cfg.provider != "ollama" or "qwen3" not in cfg.model.lower():
        return messages

    patched = []
    for msg in messages:
        if msg.get("role") == "system" and "/no_think" not in msg.get("content", ""):
            patched.append({**msg, "content": "/no_think\n\n" + msg["content"]})
        else:
            patched.append(msg)
    return patched


def structured_parse(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    response_format: Type[BaseModel],
    temperature: float = 0.3,
) -> Any:
    """Wrapper around beta.chat.completions.parse() with Ollama compatibility.

    Handles max_tokens, context window sizing, and Qwen3 thinking suppression.
    Returns the parsed Pydantic object, or None if the model returned nothing.
    """
    from zil.config import get_config
    cfg = get_config()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": _patch_system_nothink(messages),
        "response_format": response_format,
        "temperature": temperature,
    }

    max_tok = cfg.effective_max_tokens
    if max_tok is not None:
        kwargs["max_tokens"] = max_tok

    extra = _build_extra_body()
    if extra:
        kwargs["extra_body"] = extra

    response = client.beta.chat.completions.parse(**kwargs)
    return response.choices[0].message.parsed


def tool_create(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict],
    tools: list[dict],
    temperature: float = 0.5,
) -> Any:
    """Wrapper around chat.completions.create() for the tool loop.

    Applies the same max_tokens and extra_body as structured_parse().
    """
    from zil.config import get_config
    cfg = get_config()

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": _patch_system_nothink(messages),
        "tools": tools,
        "tool_choice": "auto",
        "temperature": temperature,
    }

    max_tok = cfg.effective_max_tokens
    if max_tok is not None:
        kwargs["max_tokens"] = max_tok

    extra = _build_extra_body()
    if extra:
        kwargs["extra_body"] = extra

    return client.chat.completions.create(**kwargs)
