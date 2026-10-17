"""Fixtures compartidas entre módulos de prueba de VERAIA."""

from pathlib import Path

import pytest

from src.policy.config import PolicyConfig, load_policy_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = PROJECT_ROOT / "config" / "politica.yaml"


@pytest.fixture
def policy_config() -> PolicyConfig:
    """Política real cargada desde `config/politica.yaml` (rutas resueltas, no depende del cwd)."""
    return load_policy_config(POLICY_PATH)
