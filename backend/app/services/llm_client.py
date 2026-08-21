"""
LLM client with a single interface for Groq and Ollama.

Both providers expose an OpenAI-compatible REST API, so we use the `openai` SDK
pointed at the right base_url. Swap providers by setting LLM_PROVIDER in .env.

Usage:
    from app.services.llm_client import llm_chat

    response = await llm_chat(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
    )
    text = response.choices[0].message.content
"""

from openai import AsyncOpenAI

from app.config import settings


def _build_client() -> AsyncOpenAI:
    provider = settings.llm_provider.lower()

    if provider == "groq":
        return AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
    elif provider == "ollama":
        return AsyncOpenAI(
            api_key="ollama",  # Ollama ignores the key but the SDK requires a non-empty value
            base_url=f"{settings.ollama_base_url}/v1",
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use 'groq' or 'ollama'.")


def _active_model() -> str:
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return settings.groq_model
    return settings.ollama_model


async def llm_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 1024,
    response_format: dict | None = None,
) -> object:
    """
    Send a chat-completion request to whichever provider is configured.

    Args:
        messages: OpenAI-format message list, e.g. [{"role": "user", "content": "..."}]
        temperature: Sampling temperature (0 = deterministic, 1 = creative).
        max_tokens: Maximum tokens in the completion.
        response_format: Optional dict, e.g. {"type": "json_object"} for structured output.

    Returns:
        The raw OpenAI ChatCompletion response object.
        Access the text with: response.choices[0].message.content
    """
    client = _build_client()
    kwargs = dict(
        model=_active_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format

    return await client.chat.completions.create(**kwargs)
