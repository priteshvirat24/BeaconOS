"""Beacon Command — LLM Provider Abstraction.

Implements LLMProvider ABC, StructuredLLMClient, and provider implementations.
All semantic reasoning flows through this layer.
"""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from beacon.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class ModelInvocationRecord(BaseModel):
    """Record of an LLM invocation for auditing."""

    invocation_id: str
    provider: str
    model: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    latency_ms: int = 0
    status: str = "success"
    error: Optional[str] = None
    retry_count: int = 0


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier string."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Active model name."""
        ...

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate text from messages."""
        ...

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> T:
        """Generate structured output validated against a Pydantic schema."""
        ...


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        from google.genai import types

        client = self._get_client()

        # Convert messages to Gemini format
        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                contents.append(types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=[types.Part(text=msg["content"])],
                ))

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=system_instruction,
        )

        response = client.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        return response.text or ""

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> T:
        import json
        from google.genai import types

        client = self._get_client()

        contents = []
        system_instruction = None
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            else:
                contents.append(types.Content(
                    role="user" if msg["role"] == "user" else "model",
                    parts=[types.Part(text=msg["content"])],
                ))

        # Add schema instruction to system prompt
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        schema_instruction = (
            f"{system_instruction or ''}\n\n"
            f"You MUST respond with valid JSON matching this schema:\n{schema_json}\n"
            f"Respond ONLY with the JSON object, no other text."
        )

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=schema_instruction,
            response_mime_type="application/json",
        )

        response = client.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )

        text = response.text or "{}"
        return output_schema.model_validate_json(text)


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            kwargs: dict[str, Any] = {
                "api_key": self._api_key,
                "timeout": 30.0,
                "max_retries": 0,
            }
            if self._base_url:
                kwargs["base_url"] = self._base_url
            self._client = OpenAI(**kwargs)
        return self._client

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> T:
        import json

        client = self._get_client()

        # Add schema instruction
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        enhanced_messages = list(messages)

        # Find or add system message
        system_found = False
        for i, msg in enumerate(enhanced_messages):
            if msg["role"] == "system":
                enhanced_messages[i] = {
                    "role": "system",
                    "content": (
                        f"{msg['content']}\n\n"
                        f"Respond with valid JSON matching this schema:\n{schema_json}"
                    ),
                }
                system_found = True
                break
        if not system_found:
            enhanced_messages.insert(0, {
                "role": "system",
                "content": f"Respond with valid JSON matching this schema:\n{schema_json}",
            })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": enhanced_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or "{}"
        return output_schema.model_validate_json(text)


def coerce_json_schema_output(text: str, output_schema: Type[T]) -> T:
    """Resiliently parse and coerce JSON output to match Pydantic schema."""
    import json
    
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        data = json.loads(stripped)
    except Exception:
        return output_schema.model_validate_json(stripped)

    # Resilient list coercion helper
    def coerce_value(val: Any) -> Any:
        if isinstance(val, list):
            new_list = []
            for item in val:
                if isinstance(item, dict):
                    str_val = None
                    for k in ["fallback", "text", "description", "statement", "value", "objective", "name"]:
                        if k in item and isinstance(item[k], str):
                            str_val = item[k]
                            break
                    if str_val is None:
                        for k, v in item.items():
                            if isinstance(v, str):
                                str_val = v
                                break
                    if str_val is not None:
                        new_list.append(str_val)
                    else:
                        new_list.append(json.dumps(item))
                else:
                    new_list.append(str(item))
            return new_list
        return val

    try:
        schema_fields = getattr(output_schema, "model_fields", {})
        for field_name, field_info in schema_fields.items():
            if field_name in data:
                annotation_str = str(field_info.annotation)
                if "list" in annotation_str.lower() and "str" in annotation_str.lower():
                    data[field_name] = coerce_value(data[field_name])
        return output_schema.model_validate(data)
    except Exception:
        return output_schema.model_validate_json(text)


class FreeLLMAPIProvider(OpenAIProvider):
    """FreeLLMAPI LLM provider used as a first fallback."""

    def __init__(self, api_key: str, base_url: str, model: str = "auto"):
        super().__init__(api_key=api_key, model=model, base_url=base_url)

    @property
    def provider_name(self) -> str:
        return "freellmapi"

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> T:
        import json
        client = self._get_client()

        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        enhanced_messages = list(messages)

        system_found = False
        for i, msg in enumerate(enhanced_messages):
            if msg["role"] == "system":
                enhanced_messages[i] = {
                    "role": "system",
                    "content": (
                        f"{msg['content']}\n\n"
                        f"Respond with valid JSON matching this schema:\n{schema_json}"
                    ),
                }
                system_found = True
                break
        if not system_found:
            enhanced_messages.insert(0, {
                "role": "system",
                "content": f"Respond with valid JSON matching this schema:\n{schema_json}",
            })

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": enhanced_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if max_tokens:
            kwargs["max_tokens"] = max_tokens

        response = client.chat.completions.create(**kwargs)
        text = response.choices[0].message.content or "{}"
        return coerce_json_schema_output(text, output_schema)


class MistralProvider(LLMProvider):
    """Mistral LLM provider used as a fallback."""

    def __init__(self, api_key: str, model: str = "mistral-large-latest"):
        self._api_key = api_key
        self._model = model
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from mistralai.client import Mistral
            self._client = Mistral(api_key=self._api_key, timeout_ms=90000)
        return self._client

    @property
    def provider_name(self) -> str:
        return "mistral"

    @property
    def model_name(self) -> str:
        return self._model

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> str:
        client = self._get_client()
        response = client.chat.complete(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> T:
        import json
        client = self._get_client()
        schema_json = json.dumps(output_schema.model_json_schema(), indent=2)
        
        enhanced_messages = []
        has_system = False
        for msg in messages:
            if msg["role"] == "system":
                enhanced_messages.append({
                    "role": "system",
                    "content": (
                        f"{msg['content']}\n\n"
                        f"You MUST respond with valid JSON matching this schema:\n{schema_json}\n"
                        f"Respond ONLY with the JSON object, no other text."
                    )
                })
                has_system = True
            else:
                enhanced_messages.append(msg)
                
        if not has_system:
            enhanced_messages.insert(0, {
                "role": "system",
                "content": (
                    f"You MUST respond with valid JSON matching this schema:\n{schema_json}\n"
                    f"Respond ONLY with the JSON object, no other text."
                )
            })

        response = client.chat.complete(
            model=self._model,
            messages=enhanced_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or "{}"
        return coerce_json_schema_output(text, output_schema)


class StructuredLLMClient:
    """High-level client that wraps LLMProvider with retry, validation, and audit."""

    def __init__(
        self,
        provider: LLMProvider,
        max_retries: int = 3,
        prompt_version: int = 1,
    ):
        self.provider = provider
        self.max_retries = max_retries
        self.prompt_version = prompt_version
        self._fallback_providers: list[LLMProvider] = []
        self._fallbacks_resolved = False

    def _get_fallback_providers(self) -> list[LLMProvider]:
        if not self._fallbacks_resolved:
            try:
                from beacon.config import get_settings
                settings = get_settings()
                
                # 1. First Fallback: FreeLLMAPI
                if settings.freellmapi_api_key and settings.freellmapi_base_url:
                    self._fallback_providers.append(
                        FreeLLMAPIProvider(
                            api_key=settings.freellmapi_api_key,
                            base_url=settings.freellmapi_base_url,
                            model="auto",
                        )
                    )
                
                # 2. Second Fallback: Mistral
                if settings.mistral_api_key:
                    self._fallback_providers.append(
                        MistralProvider(
                            api_key=settings.mistral_api_key,
                            model=settings.mistral_model or "mistral-large-latest",
                        )
                    )
            except Exception:
                pass
            self._fallbacks_resolved = True
        return self._fallback_providers

    async def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[str, ModelInvocationRecord]:
        """Generate text with retry and fallback chain."""
        invocation_id = str(uuid.uuid4())
        start = time.monotonic()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                result = await self.provider.generate(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
                latency = int((time.monotonic() - start) * 1000)
                record = ModelInvocationRecord(
                    invocation_id=invocation_id,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    latency_ms=latency,
                    status="success",
                    retry_count=attempt,
                )
                return result, record

            except Exception as e:
                last_error = e
                logger.warning(
                    "generation_retry",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    error=str(e),
                    agent_id=agent_id,
                )
                if attempt < self.max_retries - 1:
                    import asyncio
                    sleep_time = 5 * (attempt + 1)
                    await asyncio.sleep(sleep_time)

        # Fallback Chain
        for fallback in self._get_fallback_providers():
            if fallback.provider_name == self.provider.provider_name:
                continue

            logger.warning(
                "generation_fallback_triggered",
                original_provider=self.provider.provider_name,
                fallback_provider=fallback.provider_name,
                agent_id=agent_id,
                error=str(last_error),
            )
            try:
                result = await fallback.generate(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
                latency = int((time.monotonic() - start) * 1000)
                record = ModelInvocationRecord(
                    invocation_id=invocation_id,
                    provider=fallback.provider_name,
                    model=fallback.model_name,
                    latency_ms=latency,
                    status="success",
                    retry_count=self.max_retries,
                )
                return result, record
            except Exception as fe:
                last_error = fe
                logger.error(
                    "generation_fallback_failed",
                    fallback_provider=fallback.provider_name,
                    agent_id=agent_id,
                    error=str(fe),
                )

        latency = int((time.monotonic() - start) * 1000)
        record = ModelInvocationRecord(
            invocation_id=invocation_id,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            latency_ms=latency,
            status="error",
            error=str(last_error),
            retry_count=self.max_retries,
        )
        raise last_error

    async def generate_structured(
        self,
        messages: list[dict[str, str]],
        output_schema: Type[T],
        *,
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        agent_id: Optional[str] = None,
    ) -> tuple[T, ModelInvocationRecord]:
        """Generate structured output with retry and fallback chain."""
        invocation_id = str(uuid.uuid4())
        start = time.monotonic()
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                result = await self.provider.generate_structured(
                    messages,
                    output_schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency = int((time.monotonic() - start) * 1000)
                record = ModelInvocationRecord(
                    invocation_id=invocation_id,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    latency_ms=latency,
                    status="success",
                    retry_count=attempt,
                )
                return result, record

            except Exception as e:
                last_error = e
                logger.warning(
                    "structured_generation_retry",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    error=str(e),
                    agent_id=agent_id,
                )
                if attempt < self.max_retries - 1:
                    import asyncio
                    sleep_time = 5 * (attempt + 1)
                    await asyncio.sleep(sleep_time)

        # Fallback Chain
        for fallback in self._get_fallback_providers():
            if fallback.provider_name == self.provider.provider_name:
                continue

            logger.warning(
                "structured_generation_fallback_triggered",
                original_provider=self.provider.provider_name,
                fallback_provider=fallback.provider_name,
                agent_id=agent_id,
                error=str(last_error),
            )
            try:
                result = await fallback.generate_structured(
                    messages,
                    output_schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                latency = int((time.monotonic() - start) * 1000)
                record = ModelInvocationRecord(
                    invocation_id=invocation_id,
                    provider=fallback.provider_name,
                    model=fallback.model_name,
                    latency_ms=latency,
                    status="success",
                    retry_count=self.max_retries,
                )
                return result, record
            except Exception as fe:
                last_error = fe
                logger.error(
                    "structured_generation_fallback_failed",
                    fallback_provider=fallback.provider_name,
                    agent_id=agent_id,
                    error=str(fe),
                )

        latency = int((time.monotonic() - start) * 1000)
        record = ModelInvocationRecord(
            invocation_id=invocation_id,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            latency_ms=latency,
            status="error",
            error=str(last_error),
            retry_count=self.max_retries,
        )
        raise last_error  # type: ignore[misc]


def create_llm_provider(settings: Any) -> LLMProvider:
    """Factory to create the configured LLM provider."""
    from beacon.config import LLMProviderType

    if settings.llm_provider == LLMProviderType.GEMINI:
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.effective_llm_model,
        )
    elif settings.llm_provider == LLMProviderType.OPENAI:
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.effective_llm_model,
            base_url=settings.openai_base_url or None,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
