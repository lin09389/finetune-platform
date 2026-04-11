"""Runtime-routed LLM client for intent detection."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from ai.gateway import get_provider
from security.encryption import secure_storage

logger = logging.getLogger(__name__)


class RoutedIntentLLMClient:
    """Route intent-LLM calls to the current session backend/model."""

    def __init__(
        self,
        *,
        backend: str | None,
        model: str | None,
        ollama_base_url: str,
        timeout_ms: int = 1500,
        provider: str | None = None,
        api_key: str | None = None,
        group_id: str | None = None,
        base_url: str | None = None,
        version: str | None = None,
    ) -> None:
        self.backend = (backend or "").lower().strip()
        self.model = model
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.timeout_seconds = max(timeout_ms, 100) / 1000.0
        self.provider = provider
        self.api_key = api_key
        self.group_id = group_id or ""
        self.base_url = base_url or ""
        self.version = version or ""

    def generate(self, prompt: str) -> str:
        if not prompt.strip():
            return ""

        if self.backend == "ollama":
            return self._generate_with_ollama(prompt)
        if self.backend == "cloud":
            return self._generate_with_cloud(prompt)
        return ""

    def _generate_with_ollama(self, prompt: str) -> str:
        model = self.model or "qwen2.5:7b"
        chat_payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 400,
            },
        }
        generate_payload = {
            "model": model,
            "prompt": (
                "Return valid JSON only.\n\n"
                + prompt
            ),
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 400,
            },
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(f"{self.ollama_base_url}/api/chat", json=chat_payload)
                if response.status_code == 404:
                    response = client.post(f"{self.ollama_base_url}/api/generate", json=generate_payload)
                    response.raise_for_status()
                    data = response.json()
                    return str(data.get("response") or "")
                response.raise_for_status()
                data = response.json()
                return str((data.get("message") or {}).get("content") or "")
        except Exception as exc:  # pragma: no cover - runtime fallback path
            logger.warning("Intent LLM (ollama) failed: %s", exc)
            return ""

    def _generate_with_cloud(self, prompt: str) -> str:
        provider_name = (self.provider or "").strip()
        if not provider_name:
            return ""

        api_key = self.api_key
        if not api_key:
            key_data = secure_storage.get(f"cloud_{provider_name}_key") or {}
            api_key = key_data.get("api_key", "")
            if not self.group_id:
                self.group_id = key_data.get("group_id", "") or ""
            if not self.base_url:
                self.base_url = key_data.get("base_url", "") or ""
        if not api_key:
            return ""

        provider = get_provider(
            provider_name,
            group_id=self.group_id,
            base_url=self.base_url,
            version=self.version,
        )
        if provider is None:
            return ""

        async def _call() -> str:
            response = await provider.chat(
                messages=[
                    {"role": "system", "content": "Return valid JSON only."},
                    {"role": "user", "content": prompt},
                ],
                model=self.model or provider.get_default_model(),
                api_key=api_key,
                temperature=0.1,
                max_tokens=400,
            )
            return str(response.get("content", ""))

        try:
            try:
                asyncio.get_running_loop()
                return ""
            except RuntimeError:
                return asyncio.run(_call())
        except Exception as exc:  # pragma: no cover - runtime fallback path
            logger.warning("Intent LLM (cloud) failed: %s", exc)
            return ""


def build_routed_intent_llm_client(
    context: dict[str, Any] | None,
    ollama_base_url: str,
    *,
    timeout_ms: int = 1500,
) -> RoutedIntentLLMClient | None:
    if not context:
        return None

    backend = context.get("backend")
    model = context.get("model")
    provider = context.get("provider") or context.get("cloud_provider")
    api_key = context.get("api_key")
    group_id = context.get("group_id")
    base_url = context.get("base_url")
    version = context.get("version")

    if backend not in {"ollama", "cloud"}:
        return None

    return RoutedIntentLLMClient(
        backend=str(backend),
        model=str(model) if isinstance(model, str) and model else None,
        ollama_base_url=ollama_base_url,
        timeout_ms=timeout_ms,
        provider=str(provider) if isinstance(provider, str) and provider else None,
        api_key=str(api_key) if isinstance(api_key, str) and api_key else None,
        group_id=str(group_id) if isinstance(group_id, str) and group_id else None,
        base_url=str(base_url) if isinstance(base_url, str) and base_url else None,
        version=str(version) if isinstance(version, str) and version else None,
    )
