"""Beacon Command — Application Configuration.

Uses pydantic-settings with fail-fast validation for required configuration.
All environment variables are documented in .env.example.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProviderType(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"


class EmbeddingProviderType(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"


class WeatherProviderType(str, Enum):
    NWS = "nws"


class GeocodingProviderType(str, Enum):
    NOMINATIM = "nominatim"


class RoutingProviderType(str, Enum):
    OSRM = "osrm"


class ResourceProviderType(str, Enum):
    POSTGRES = "postgres"


class BeaconSettings(BaseSettings):
    """Central configuration for Beacon Command.

    Groups all settings by subsystem. Required variables fail fast on startup
    when missing. Optional variables use sensible defaults.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application ---
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_public_base_url: str = ""
    log_level: str = "INFO"

    # --- Database ---
    database_url: str = "postgresql+asyncpg://beacon:beacon@localhost:5432/beacon"
    database_sync_url: str = "postgresql+psycopg://beacon:beacon@localhost:5432/beacon"

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Slack ---
    slack_bot_token: str = ""
    slack_coordinator_user_token: str = ""
    slack_signing_secret: str = ""
    slack_app_token: str = ""
    slack_default_alert_channel: str = ""
    slack_volunteers_channel: str = ""
    slack_operations_channel: str = ""
    slack_app_home_enabled: bool = True

    # --- Slack Search (RTS) ---
    slack_rts_base_url: str = "https://slack.com/api"
    slack_rts_timeout_seconds: int = 20

    # --- LLM Provider ---
    llm_provider: LLMProviderType = LLMProviderType.GEMINI
    llm_model: str = ""
    llm_temperature: float = 0.1
    llm_max_output_tokens: Optional[int] = None

    # --- Gemini ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o"

    # --- Mistral ---
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"

    # --- Embeddings ---
    embedding_provider: EmbeddingProviderType = EmbeddingProviderType.GEMINI
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 768

    # --- USGS ---
    usgs_feed_url: str = (
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"
    )
    usgs_poll_interval_seconds: int = 60

    # --- GDACS ---
    gdacs_feed_url: str = "https://www.gdacs.org/xml/rss.xml"
    gdacs_poll_interval_seconds: int = 300

    # --- Weather ---
    weather_provider: WeatherProviderType = WeatherProviderType.NWS
    weather_api_key: str = ""
    weather_base_url: str = ""

    # --- Geocoding ---
    geocoding_provider: GeocodingProviderType = GeocodingProviderType.NOMINATIM
    geocoding_api_key: str = ""
    geocoding_base_url: str = ""

    # --- Routing ---
    routing_provider: RoutingProviderType = RoutingProviderType.OSRM
    routing_api_key: str = ""
    routing_base_url: str = ""

    # --- Resource ---
    resource_provider: ResourceProviderType = ResourceProviderType.POSTGRES
    resource_api_key: str = ""
    resource_base_url: str = ""

    # --- LangSmith ---
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "beacon-command"

    # --- OpenTelemetry ---
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "beacon-command"

    # --- MCP Server URLs ---
    mcp_hazard_server_url: str = "http://localhost:8010"
    mcp_geospatial_server_url: str = "http://localhost:8011"
    mcp_resource_server_url: str = "http://localhost:8012"
    mcp_operations_server_url: str = "http://localhost:8013"
    mcp_verification_server_url: str = "http://localhost:8014"

    # --- Agent Settings ---
    agent_default_tool_budget: int = 12
    agent_default_token_budget: Optional[int] = None
    agent_default_timeout_seconds: int = 120
    mission_max_retries: int = 3
    mission_max_depth: int = 12
    max_parallel_missions: int = 6

    # --- Hazard Thresholds ---
    hazard_min_magnitude: float = 4.0
    hazard_min_severity_score: float = 3.0
    hazard_max_depth_km: float = 70.0
    hazard_relevance_threshold: float = 0.3

    # --- Epistemic Thresholds ---
    claim_default_freshness_minutes: int = 60
    claim_verification_threshold: float = 0.7
    contradiction_threshold: float = 0.5
    material_change_threshold: float = 0.6
    intelligence_gap_priority_threshold: float = 0.4

    # --- Policy ---
    human_approval_required_for_operational_writes: bool = True
    auto_create_crisis_channel: bool = False
    auto_create_draft_tasks: bool = False

    # --- Prompts ---
    prompt_version: int = 1

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in valid:
            raise ValueError(f"log_level must be one of {valid}, got {v}")
        return upper

    @property
    def effective_llm_model(self) -> str:
        """Return the model name for the active provider."""
        if self.llm_model:
            return self.llm_model
        if self.llm_provider == LLMProviderType.GEMINI:
            return self.gemini_model
        return self.openai_model

    @property
    def is_slack_configured(self) -> bool:
        return bool(self.slack_bot_token and self.slack_signing_secret)

    @property
    def is_llm_configured(self) -> bool:
        if self.llm_provider == LLMProviderType.GEMINI:
            return bool(self.gemini_api_key)
        return bool(self.openai_api_key)

    def require_slack(self) -> None:
        """Fail fast if Slack is not configured."""
        if not self.slack_bot_token:
            raise ValueError("SLACK_BOT_TOKEN is required")
        if not self.slack_signing_secret:
            raise ValueError("SLACK_SIGNING_SECRET is required")

    def require_llm(self) -> None:
        """Fail fast if LLM provider is not configured."""
        if self.llm_provider == LLMProviderType.GEMINI and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.llm_provider == LLMProviderType.OPENAI and not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")


def get_settings() -> BeaconSettings:
    """Factory for settings singleton. Import and call this instead of constructing directly."""
    return BeaconSettings()
