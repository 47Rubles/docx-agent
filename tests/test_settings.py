"""Тесты загрузки конфигурации и разрешения ссылок на секреты."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.settings import (  # noqa: E402
    SecretNotConfigured,
    load_settings,
    mask_secrets,
    referenced_env_names,
    resolve_placeholders,
)

SETTINGS_PATH = ROOT / "config" / "settings.yaml"


def test_placeholder_resolved_from_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-value")
    assert resolve_placeholders("${LLM_API_KEY}") == "secret-value"


def test_missing_placeholder_raises(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SecretNotConfigured):
        resolve_placeholders("${LLM_API_KEY}")


def test_error_message_contains_no_secret(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(SecretNotConfigured) as excinfo:
        resolve_placeholders({"api_key": "${LLM_API_KEY}"}, fallback_env=("GEMINI_API_KEY",))
    message = str(excinfo.value)
    assert "LLM_API_KEY" in message
    assert "GEMINI_API_KEY" in message
    assert "***" not in message


def test_fallback_used_for_api_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "from-fallback")
    resolved = resolve_placeholders(
        {"llm": {"api_key": "${LLM_API_KEY}"}}, fallback_env=("GEMINI_API_KEY",)
    )
    assert resolved["llm"]["api_key"] == "from-fallback"


def test_fallback_not_applied_to_other_fields(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "from-fallback")
    with pytest.raises(SecretNotConfigured):
        resolve_placeholders(
            {"llm": {"base_url": "${LLM_API_KEY}"}}, fallback_env=("GEMINI_API_KEY",)
        )


def test_load_settings_reads_repository_config(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "secret-value")
    settings = load_settings(SETTINGS_PATH)
    assert settings["llm"]["api_key"] == "secret-value"
    assert settings["llm"]["model"]
    assert "api_key_fallbacks" not in settings


def test_mask_secrets_hides_value():
    assert mask_secrets("key=abcdef123456", ["abcdef123456"]) == "key=***"


def test_repository_config_contains_no_literal_key():
    raw = SETTINGS_PATH.read_text(encoding="utf-8")
    assert "${LLM_API_KEY}" in raw
    for marker in ("AIza", "AQ.Ab", "ghp_", "sk-"):
        assert marker not in raw


def test_referenced_env_names():
    names = referenced_env_names({"llm": {"api_key": "${LLM_API_KEY}", "m": "${LLM_MODEL}"}})
    assert names == ["LLM_API_KEY", "LLM_MODEL"]
