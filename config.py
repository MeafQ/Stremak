from typing import Any

from pydantic import BaseModel, Field, model_validator

from metadata.tmdb import TMDBSettings
from streaming.parsing.specs import DEFAULT_PARSING_SPECS, ParsingSpecs
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


class ParsingConfig(BaseModel):
    specs: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        return {} if value is None else value

    def effective_specs(self, base: ParsingSpecs = DEFAULT_PARSING_SPECS) -> ParsingSpecs:
        return base.overlay(self.specs)


class AppConfig(BaseModel):
    parsing: ParsingConfig = Field(default_factory=ParsingConfig)
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

    @model_validator(mode="after")
    def _require_services(self) -> "AppConfig":
        self.parsing.effective_specs()
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
