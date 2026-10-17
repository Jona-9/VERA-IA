"""
Cliente LLM opcional compatible con la API de OpenAI (OpenAI, Ollama local, etc.).

Principios aplicados:
- III: el LLM solo redacta o resume; nunca decide acciones.
- XI: quien invoca este cliente es responsable de enviar únicamente contexto anonimizado.
- Demo 100% offline: si no hay configuración, `from_env()` retorna None y se usa el
  modo determinista.

Variables de entorno:
- VERAIA_LLM_BASE_URL: endpoint base (ej. http://localhost:11434/v1 para Ollama).
- VERAIA_LLM_API_KEY: clave opcional (no requerida por proveedores locales).
- VERAIA_LLM_MODEL: modelo a utilizar.
- VERAIA_LLM_TIMEOUT: tiempo máximo de respuesta en segundos (por defecto 2).
"""

import json
import os
import urllib.request
from typing import List, Dict, Optional

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 2.0


class LLMUnavailableError(RuntimeError):
    """El endpoint LLM no respondió a tiempo o devolvió una respuesta inválida."""


class LLMClient:
    """Cliente mínimo de chat completions sin dependencias externas."""

    def __init__(
        self,
        base_url: str,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> Optional["LLMClient"]:
        """Construye el cliente desde variables de entorno, o None si no está configurado."""
        base_url = os.environ.get("VERAIA_LLM_BASE_URL")
        api_key = os.environ.get("VERAIA_LLM_API_KEY")
        if not base_url and not api_key:
            return None
        return cls(
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            model=os.environ.get("VERAIA_LLM_MODEL", DEFAULT_MODEL),
            api_key=api_key,
            timeout_seconds=float(os.environ.get("VERAIA_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        )

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Envía la conversación y retorna el contenido de la primera respuesta."""
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": temperature}
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # red, timeout, JSON o estructura inesperada
            raise LLMUnavailableError(str(exc)) from exc
