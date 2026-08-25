"""
LLM client with a single interface for Groq, Gemini, and Ollama.

Groq and Ollama expose an OpenAI-compatible REST API, so the `openai` SDK
pointed at the right base_url works for both. Gemini does NOT reliably work
through that OpenAI-compat shim with this project's API key format, so Gemini
uses Google's native `google-genai` SDK instead — its response is adapted
back into the same OpenAI-shaped object so callers don't need to branch.

Swap providers by setting LLM_PROVIDER in .env.

Usage:
    from app.services.llm_client import llm_chat

    response = await llm_chat(
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.7,
    )
    text = response.choices[0].message.content
"""

from openai import AsyncOpenAI
from google import genai
from google.genai import types as genai_types

from app.config import settings


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _ChatCompletion:
    """Adapter so Gemini responses look like an OpenAI ChatCompletion."""

    def __init__(self, content: str):
        self.choices = [_Choice(content)]


def _build_openai_client() -> AsyncOpenAI:
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
        raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Use 'groq', 'gemini', or 'ollama'.")


def _active_model() -> str:
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return settings.groq_model
    if provider == "gemini":
        return settings.gemini_model
    return settings.ollama_model


def _split_messages(messages: list[dict]) -> tuple[str | None, list[genai_types.Content]]:
    """Split OpenAI-style messages into a Gemini system_instruction + contents list."""
    system_instruction = None
    contents: list[genai_types.Content] = []

    for msg in messages:
        role = msg["role"]
        text = msg["content"]
        if role == "system":
            # Gemini takes one system_instruction; concatenate if there's more than one.
            system_instruction = f"{system_instruction}\n\n{text}" if system_instruction else text
        else:
            gemini_role = "model" if role == "assistant" else "user"
            contents.append(
                genai_types.Content(role=gemini_role, parts=[genai_types.Part(text=text)])
            )

    return system_instruction, contents


async def _gemini_chat(
    messages: list[dict],
    temperature: float,
    max_tokens: int,
    response_format: dict | None,
) -> _ChatCompletion:
    client = genai.Client(api_key=settings.gemini_api_key)
    system_instruction, contents = _split_messages(messages)

    config_kwargs = dict(
        temperature=temperature,
        max_output_tokens=max_tokens,
        # This app only narrates pre-computed data — no reasoning needed, and
        # thinking tokens otherwise eat the max_output_tokens budget and cause
        # slow, truncated responses. Gemini 3.x models don't allow fully
        # disabling thinking (thinking_budget=0 -> 400), so turn it down instead.
        thinking_config=genai_types.ThinkingConfig(thinking_level=genai_types.ThinkingLevel.MINIMAL),
        # No tools are passed, so silence the SDK's "use AsyncChat instead" AFC warning.
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
    )
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if response_format and response_format.get("type") == "json_object":
        config_kwargs["response_mime_type"] = "application/json"

    response = await client.aio.models.generate_content(
        model=_active_model(),
        contents=contents,
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )

    text = (response.text or "").strip()
    return _ChatCompletion(text)


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
        An object shaped like an OpenAI ChatCompletion.
        Access the text with: response.choices[0].message.content
    """
    provider = settings.llm_provider.lower()

    if provider == "gemini":
        return await _gemini_chat(messages, temperature, max_tokens, response_format)

    client = _build_openai_client()
    kwargs = dict(
        model=_active_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if response_format:
        kwargs["response_format"] = response_format

    return await client.chat.completions.create(**kwargs)
