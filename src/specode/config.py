"""Configuration loading for specode."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


DEFAULT_MODEL_NAME = "openai:gpt-5.2"


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing."""


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from the environment."""

    openai_api_key: str
    model_name: str = DEFAULT_MODEL_NAME


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

