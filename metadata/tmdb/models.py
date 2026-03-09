from datetime import date
from functools import cached_property

from pydantic import BaseModel, ConfigDict, Field, computed_field

from languages import CountryCode, LangCode, country_to_lang


class TmdbModel(BaseModel):
    model_config = ConfigDict(frozen=True)

class AltTitle(TmdbModel):
    iso_3166_1: CountryCode
    title: str

    @computed_field
    @cached_property
    def lang(self) -> LangCode:
        return country_to_lang(self.iso_3166_1)

class AltTitlesResponse(TmdbModel):
    results: list[AltTitle] = []
    titles: list[AltTitle] = []

    @property
    def all(self) -> list[AltTitle]:
        return self.results or self.titles

class BaseResult(TmdbModel):    
    id: int
    title: str
    original_title: str # NOTE Does it ever return "" ?
    original_language: LangCode # NOTE Does it ever return "" ?
    release_date: date # NOTE Does it ever return "" ?
    popularity: float

class MovieResult(BaseResult): ...

class SeriesResult(BaseResult):
    title: str = Field(validation_alias="name")
    original_title: str = Field(validation_alias="original_name")
    release_date: date = Field(validation_alias="first_air_date")
    
class FindResponse(BaseModel):
    movie_results: list[MovieResult] = []
    tv_results: list[SeriesResult] = []

    @property
    def first(self) -> MovieResult | SeriesResult | None:
        if self.tv_results:
            return self.tv_results[0]
        if self.movie_results:
            return self.movie_results[0]
        return None