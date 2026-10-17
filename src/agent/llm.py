"""
Cliente LLM opcional compatible con la API de OpenAI y OpenRouter.

Principios aplicados:
- III: el LLM solo redacta o resume; nunca decide acciones.
- XI: quien invoca este cliente es responsable de enviar únicamente contexto anonimizado.
- Demo 100% offline: si no hay configuración, `from_env()` retorna None y se usa el
  modo determinista.

Variables de entorno:
- VERAIA_LLM_BASE_URL: endpoint base (ej. https://openrouter.ai/api/v1 o http://localhost:11434/v1).
- VERAIA_LLM_API_KEY: clave API (ej. clave OpenRouter sk-or-v1-...).
- VERAIA_LLM_MODEL: modelo a utilizar (ej. openai/gpt-4o-mini).
- VERAIA_LLM_TIMEOUT: tiempo máximo de respuesta en segundos (por defecto 10.0).
"""

from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_TIMEOUT_SECONDS = 10.0


def _load_env_file() -> None:
    """Carga variables desde el archivo .env si existe en la raíz."""
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ.setdefault(key, val)


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
        if os.environ.get("VERAIA_TEST_MODE") == "1" or os.environ.get("PYTEST_CURRENT_TEST"):
            return None
        _load_env_file()
        api_key = os.environ.get("VERAIA_LLM_API_KEY")
        base_url = os.environ.get("VERAIA_LLM_BASE_URL")

        if not base_url and not api_key:
            return None

        # Autodetección de OpenRouter según el prefijo de la clave
        if api_key and api_key.startswith("sk-or-") and not base_url:
            base_url = DEFAULT_OPENROUTER_BASE_URL

        default_model = "openai/gpt-4o-mini" if (base_url and "openrouter" in base_url) else "gpt-4o-mini"
        model = os.environ.get("VERAIA_LLM_MODEL", default_model)
        timeout = float(os.environ.get("VERAIA_LLM_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))

        return cls(
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout,
        )

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> str:
        """Envía la conversación y retorna el contenido de la primera respuesta."""
        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": temperature}
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Jona-9/VERA-IA",
            "X-Title": "VERA",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except Exception as exc:  # red, timeout, JSON o estructura inesperada
            raise LLMUnavailableError(str(exc)) from exc
