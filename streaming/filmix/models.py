from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, computed_field


class FilmixModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_by_name=True)

class SearchGenre(FilmixModel):
    id: int
    name: str
    alt_name: str

class SearchStatus(FilmixModel):
    comment: str | None = None
    status: int | None = None
    status_text: str | None = None


class SearchSeriesPosition(FilmixModel):
    season: int | None = None
    episode: int | str | None = None
    translation: str | None = None
    date: datetime | None = None


class SearchItem(FilmixModel):
    id: int | str
    title: str
    year: int
    original_title: str | None = Field(default=None, alias="original_name")
    votes_pos: int | None = Field(default=None, alias="votesPos")
    votes_neg: int | None = Field(default=None, alias="votesNeg")
    poster: str | None = None
    quality: str | None = None
    status: SearchStatus | None = None
    url: str | None = None
    last_episode: SearchSeriesPosition | None = None
    max_episode: SearchSeriesPosition | None = None
    genres: list[SearchGenre] = Field(default_factory=list)

class TokenResponse(FilmixModel):
    token: str
    code: str
    expire: datetime

class UserInfo(FilmixModel):
    user_id: int
    email: str
    login: str
    display_name: str | None = None
    avatar: str | None = None
    is_pro: bool = False
    is_pro_plus: bool = False
    pro_date: datetime | None = None
    pro_days_left: int | None = None
    server: str | None = None

    @computed_field
    @property
    def name(self) -> str:
        if self.display_name and self.display_name != "-":
            return self.display_name
        return self.login

class SuggestionsResponse(FilmixModel):
    status: str
    page: int | None = None
    has_next_page: bool = False
    items: list[SearchItem] = Field(default_factory=list)

class VideoFile(FilmixModel):
    url: str
    quality: int
    pro_plus: bool = Field(alias="proPlus")

class BaseStream(FilmixModel):
    files: list[VideoFile] = []

class MovieStream(BaseStream):
    voiceover: str

class EpisodeStream(BaseStream):
    episode: int

class SeasonData(FilmixModel):
    season: int
    episodes: dict[str, EpisodeStream] = {}

SeriesPlaylist = TypeAdapter(dict[str, dict[str, SeasonData]])
ServerList = TypeAdapter(dict[str, str])
MoviesList = TypeAdapter(list[MovieStream])
