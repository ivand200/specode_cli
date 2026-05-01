"""Configuration loading for specode."""

import os
from dataclasses import dataclass, field
from typing import Final

from dotenv import load_dotenv
from pydantic_ai.settings import ModelSettings, ThinkingEffort

DEFAULT_MODEL_NAME: Final = "openai:gpt-5.4-mini"
DEFAULT_REASONING_EFFORT: Final[ThinkingEffort] = "xhigh"
DEFAULT_MODEL_SETTINGS: Final[ModelSettings] = {"thinking": DEFAULT_REASONING_EFFORT}


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from the environment."""

    openai_api_key: str
    model_name: str = DEFAULT_MODEL_NAME
    model_settings: ModelSettings = field(default_factory=lambda: DEFAULT_MODEL_SETTINGS.copy())


def load_settings() -> Settings:
    """Load and validate the runtime settings for specode."""
    load_dotenv(override=False)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ConfigurationError(
            "Missing OPENAI_API_KEY. Add it to your environment or local .env file. "
            "See .env.example for the expected format."
        )

    return Settings(openai_api_key=api_key)
