import pytest

from specode.config import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_SETTINGS,
    DEFAULT_REASONING_EFFORT,
    ConfigurationError,
    load_settings,
)


def test_raises_a_clear_error_when_openai_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert "OPENAI_API_KEY" in str(exc_info.value)


def test_default_model_settings_are_loaded_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    settings = load_settings()

    assert DEFAULT_MODEL_NAME == "openai:gpt-5.4-mini"
    assert DEFAULT_REASONING_EFFORT == "xhigh"
    assert DEFAULT_MODEL_SETTINGS == {"thinking": "xhigh"}
    assert settings.model_name == DEFAULT_MODEL_NAME
    assert settings.model_settings == DEFAULT_MODEL_SETTINGS
    assert settings.model_settings is not DEFAULT_MODEL_SETTINGS
