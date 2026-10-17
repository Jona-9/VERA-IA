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
from pathlib import Path
from typing import List, Dict, Optional

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _load_env_file() -> None:
    """Carga variables desde el archivo .env del proyecto si no están definidas."""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if env_file.exists():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


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
        _load_env_file()
        base_url = os.environ.get("VERAIA_LLM_BASE_URL")
        api_key = os.environ.get("VERAIA_LLM_API_KEY")
        if not base_url and not api_key:
            return None

        # Auto-detección de OpenRouter por formato de key
        if api_key and api_key.startswith("sk-or-v1-"):
            base_url = base_url or DEFAULT_OPENROUTER_BASE_URL
            model = os.environ.get("VERAIA_LLM_MODEL", "openai/gpt-4o-mini")
        else:
            base_url = base_url or DEFAULT_OPENAI_BASE_URL
            model = os.environ.get("VERAIA_LLM_MODEL", DEFAULT_MODEL)

        return cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=float(os.environ.get("VERAIA_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)),
        )

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Envía la conversación y retorna el contenido de la primera respuesta."""
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": temperature}
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://vera-ia.local",
            "X-Title": "VERA-IA",
        }
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
