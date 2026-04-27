import pytest

from specode.config import ConfigurationError, load_settings


def test_raises_a_clear_error_when_openai_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    assert "OPENAI_API_KEY" in str(exc_info.value)
