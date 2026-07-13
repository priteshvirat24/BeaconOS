"""Tests for Beacon Command — Configuration."""

import os
import pytest

from beacon.config import BeaconSettings, AppEnv, LLMProviderType


class TestBeaconSettings:
    def test_default_settings(self) -> None:
        """Settings should load with defaults."""
        settings = BeaconSettings()
        assert settings.app_env == AppEnv.DEVELOPMENT
        assert settings.app_port == 8000
        assert settings.log_level == "INFO"
        assert settings.llm_provider == LLMProviderType.GEMINI

    def test_log_level_validation(self) -> None:
        """Log level must be a valid Python log level."""
        settings = BeaconSettings(log_level="debug")
        assert settings.log_level == "DEBUG"

        with pytest.raises(ValueError):
            BeaconSettings(log_level="INVALID")

    def test_effective_llm_model_gemini(self) -> None:
        """Should return Gemini model when provider is Gemini."""
        settings = BeaconSettings(llm_provider="gemini", gemini_model="gemini-2.0-flash")
        assert settings.effective_llm_model == "gemini-2.0-flash"

    def test_effective_llm_model_openai(self) -> None:
        """Should return OpenAI model when provider is OpenAI."""
        settings = BeaconSettings(llm_provider="openai", openai_model="gpt-4o")
        assert settings.effective_llm_model == "gpt-4o"

    def test_effective_llm_model_override(self) -> None:
        """LLM_MODEL override should take precedence."""
        settings = BeaconSettings(llm_model="custom-model")
        assert settings.effective_llm_model == "custom-model"

    def test_is_slack_configured(self) -> None:
        """Slack is configured when bot token and signing secret are set."""
        settings = BeaconSettings(slack_bot_token="xoxb-test", slack_signing_secret="secret")
        assert settings.is_slack_configured is True

        settings_no_slack = BeaconSettings(slack_bot_token="", slack_signing_secret="")
        assert settings_no_slack.is_slack_configured is False

    def test_require_slack_fails(self) -> None:
        """require_slack should raise when Slack is not configured."""
        settings = BeaconSettings(slack_bot_token="")
        with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
            settings.require_slack()

    def test_require_llm_fails(self) -> None:
        """require_llm should raise when LLM is not configured."""
        settings = BeaconSettings(llm_provider="gemini", gemini_api_key="")
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            settings.require_llm()
