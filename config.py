from pydantic import BaseModel, Field, field_validator, model_validator

from metadata.tmdb import TMDBSettings
from streaming.filmix import FilmixSettings
from streaming.kinopub import KinoPubSettings


def _normalize_provider_section(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        key: provider_config
        for key, provider_config in value.items()
        if provider_config
    }


class StreamingConfig(BaseModel):
    filmix: FilmixSettings | None = None
    kinopub: KinoPubSettings | None = None


class MetadataConfig(BaseModel):
    tmdb: TMDBSettings | None = None


class AppConfig(BaseModel):
    locale: str
    streaming: StreamingConfig = Field(default_factory=StreamingConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)

    @model_validator(mode="before")
    @classmethod
    def _normalize_sections(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        return {
            **value,
            "streaming": _normalize_provider_section(value.get("streaming")),
            "metadata": _normalize_provider_section(value.get("metadata")),
        }

    @field_validator("locale")
    @classmethod
    def _validate_locale(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("locale is required")
        return value

    @model_validator(mode="after")
    def _require_services(self) -> "AppConfig":
        if not _has_streaming_service(self.streaming):
            raise ValueError("At least one streaming service is required")
        if not _has_metadata_service(self.metadata):
            raise ValueError("At least one metadata source is required")
        return self


def _has_streaming_service(config: StreamingConfig) -> bool:
    return bool(
        (config.filmix and config.filmix.is_configured())
        or (config.kinopub and config.kinopub.is_configured())
    )


def _has_metadata_service(config: MetadataConfig) -> bool:
    return bool(config.tmdb and config.tmdb.is_configured())
