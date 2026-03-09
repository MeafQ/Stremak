from pydantic import BaseModel, ConfigDict, Field, model_validator

from languages import LangCode3


class KinoPubModel(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_by_name=True)

class DeviceCodeResponse(KinoPubModel):
    code: str
    user_code: str
    verification_uri: str
    interval: int = 5
    expires_in: int = 300

class TokenResponse(KinoPubModel):
    access_token: str
    refresh_token: str
    expires_in: int

class UserProfile(KinoPubModel):
    name: str
    avatar: str

class UserSubscription(KinoPubModel):
    active: bool = False
    days: float = 0

class UserData(KinoPubModel):
    username: str
    subscription: UserSubscription
    profile: UserProfile

class UserResponse(KinoPubModel):
    status: int
    user: UserData

class SearchItem(KinoPubModel):
    id: int
    title: str
    original_title: str
    year: int
    type: str
    voice: str
    imdb: int = 0
    kinopoisk: int = 0
    finished: bool = False

    @model_validator(mode="before")
    @classmethod
    def split_title(cls, data: dict) -> dict:
        if isinstance(data, dict):
            title = data.get("title", "")
            if " / " in title:
                parts = title.split(" / ", 1)
                data = {**data, "title": parts[0], "original_title": parts[1]}
            else:
                data = {**data, "title": title, "original_title": title}
        return data

class SearchResponse(KinoPubModel):
    status: int
    items: list[SearchItem] = Field(default_factory=list)

class AudioType(KinoPubModel):
    id: int
    title: str
    short_title: str

class AudioAuthor(KinoPubModel):
    id: int
    title: str
    short_title: str | None = None

class AudioTrack(KinoPubModel):
    id: int
    index: int
    codec: str
    channels: int
    lang: LangCode3
    type: AudioType | None = None
    author: AudioAuthor | None = None

class FileUrl(KinoPubModel):
    http: str
    hls: str
    hls2: str
    hls4: str

class VideoFile(KinoPubModel):
    codec: str
    w: int
    h: int
    quality: str
    quality_id: int
    file: str
    url: FileUrl

class Subtitle(KinoPubModel):
    lang: str # Quite often empty but one time I saw 'ai'
    url: str

class Episode(KinoPubModel):
    id: int
    number: int
    title: str = ""
    audios: list[AudioTrack] = Field(default_factory=list)
    subtitles: list[Subtitle] = Field(default_factory=list)
    files: list[VideoFile] = Field(default_factory=list)

class Season(KinoPubModel):
    id: int
    number: int
    episodes: list[Episode] = Field(default_factory=list)

class ItemDetail(KinoPubModel):
    id: int
    type: str
    title: str
    year: int
    quality: int = 0
    imdb: int = 0
    kinopoisk: int | None = None
    seasons: list[Season] | None = None
    videos: list[Episode] | None = None

class ItemResponse(KinoPubModel):
    status: int
    item: ItemDetail

class DeviceInfo(KinoPubModel):
    id: int
    title: str
    hardware: str
    software: str

class DeviceInfoResponse(KinoPubModel):
    status: int
    device: DeviceInfo
