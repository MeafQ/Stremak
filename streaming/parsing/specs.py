from collections.abc import Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from .models import Media, Track


def _deep_merge(base: dict[str, Any], overlay: Mapping[str, object]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


class ValueSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: int = 0
    label: str | None = None
    code: str | None = None
    msgid: str | None = None
    hidden: bool = False
    webgui: bool = False


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[str, ValueSpec]

    def __getitem__(self, value_id: str) -> ValueSpec:
        return self.values[value_id]

    @computed_field
    @property
    def ui_values(self) -> dict[str, ValueSpec]:
        return {
            value_id: value
            for value_id, value in self.values.items()
            if value.webgui
        }

    @computed_field
    @property
    def default_scores(self) -> dict[str, int]:
        return {value_id: value.score for value_id, value in self.ui_values.items()}


class MarkerValueSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    score: int | None = None
    label: str | None = None
    code: str | None = None
    msgid: str | None = None
    hidden: bool | None = None
    confidence: int | None = None
    anchored: bool | None = None


class MarkerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pattern: str
    blocked: tuple[str, ...] = ()
    attrs: dict[str, MarkerValueSpec]

    @model_validator(mode="after")
    def _validate(self) -> Self:
        overlap = set(self.attrs) & set(self.blocked)
        if overlap:
            names = ", ".join(sorted(overlap))
            raise ValueError(f"Marker cannot both set and block the same field(s): {names}")
        return self


class ParsingSpecs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attrs: dict[str, FieldSpec]
    markers: dict[str, dict[str, MarkerSpec]] = Field(default_factory=dict)
    ignored_patterns: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate(self) -> Self:
        expected_attrs = set(Track.attr_ids()) | set(Media.attr_ids())
        missing_attrs = expected_attrs - set(self.attrs)
        if missing_attrs:
            names = ", ".join(sorted(missing_attrs))
            raise ValueError(f"Missing attr specs: {names}")

        extra_attrs = set(self.attrs) - expected_attrs
        if extra_attrs:
            names = ", ".join(sorted(extra_attrs))
            raise ValueError(f"Unknown attr specs: {names}")

        expected_groups = {Track.PARSING_GROUP, Media.PARSING_GROUP}
        extra_groups = set(self.markers) - expected_groups
        if extra_groups:
            names = ", ".join(sorted(extra_groups))
            raise ValueError(f"Unknown marker groups: {names}")

        self._validate_marker_group(Track)
        self._validate_marker_group(Media)
        return self

    def _validate_marker_group(self, owner: type[Track] | type[Media]) -> None:
        attr_ids = set(owner.attr_ids())
        allowed_ids = set(owner.marker_attr_ids())
        for marker_id, marker in self.markers_for(owner.PARSING_GROUP).items():
            for attr_id, value_spec in marker.attrs.items():
                if attr_id not in allowed_ids:
                    raise ValueError(f"Unknown {owner.PARSING_GROUP} marker field '{attr_id}' in '{marker_id}'")
                if attr_id in attr_ids and value_spec.id not in self.attrs[attr_id].values:
                    raise ValueError(f"Unknown value '{value_spec.id}' for {owner.PARSING_GROUP} marker field '{attr_id}'")
            for blocked_attr in marker.blocked:
                if blocked_attr not in allowed_ids:
                    raise ValueError(f"Unknown blocked {owner.PARSING_GROUP} marker field '{blocked_attr}' in '{marker_id}'")

    def overlay(self, overlay: Mapping[str, object] | None) -> "ParsingSpecs":
        if not overlay:
            return self
        merged = _deep_merge(
            self.model_dump(mode="python", exclude_computed_fields=True),
            overlay,
        )
        return ParsingSpecs.model_validate(merged)

    def attr(self, attr_id: str) -> FieldSpec:
        return self.attrs[attr_id]

    def markers_for(self, owner: str | type[Track] | type[Media]) -> dict[str, MarkerSpec]:
        group = owner if isinstance(owner, str) else owner.PARSING_GROUP
        return self.markers.get(group, {})


DEFAULT_TRACK_ATTR_SPECS = {
    "lang": FieldSpec(values={
        "ru": ValueSpec(code="RU", label="Русский", score=3000, webgui=True),
        "uk": ValueSpec(code="UK", label="Українська", score=2000, webgui=True),
        "en": ValueSpec(code="EN", label="English", score=1000, webgui=True),
        "de": ValueSpec(),
        "fr": ValueSpec(),
        "es": ValueSpec(),
        "it": ValueSpec(),
        "pt": ValueSpec(),
        "nl": ValueSpec(),
        "sv": ValueSpec(),
        "no": ValueSpec(),
        "da": ValueSpec(),
        "fi": ValueSpec(),
        "pl": ValueSpec(),
        "cs": ValueSpec(),
        "hu": ValueSpec(),
        "ro": ValueSpec(),
        "el": ValueSpec(),
        "zh": ValueSpec(),
        "ja": ValueSpec(),
        "ko": ValueSpec(),
        "hi": ValueSpec(),
        "th": ValueSpec(),
        "id": ValueSpec(),
        "vi": ValueSpec(),
        "ms": ValueSpec(),
    }),
    "voice_type": FieldSpec(values={
        "DUB": ValueSpec(score=70, label="DUB"),
        "MVO": ValueSpec(score=30, label="MVO"),
        "DVO": ValueSpec(label="DVO"),
        "AVO": ValueSpec(score=-10, label="AVO"),
        "OG": ValueSpec(score=-40, label="OG"),
    }),
    "official": FieldSpec(values={
        "official": ValueSpec(score=30, msgid="official.official"),
        "unofficial": ValueSpec(msgid="official.unofficial"),
    }),
    "audio_format": FieldSpec(values={
        "Atmos": ValueSpec(score=20, label="🎵 Atmos"),
        "TrueHD": ValueSpec(score=15, label="🎵 TrueHD"),
        "DTS-HD": ValueSpec(score=12, label="🎵 DTS-HD"),
        "DTS": ValueSpec(score=10, label="🎵 DTS"),
        "AC3": ValueSpec(score=0, hidden=True),
        "AAC": ValueSpec(hidden=True),
    }),
    "audio_note": FieldSpec(values={
        "clean": ValueSpec(score=-10, msgid="audio_note.clean"),
    }),
    "commentary": FieldSpec(values={
        "commentary": ValueSpec(score=-50, msgid="commentary.commentary"),
    }),
    "ads": FieldSpec(values={
        "ads": ValueSpec(score=-50000, msgid="ads.ads"),
    }),
    "mature": FieldSpec(values={
        "18+": ValueSpec(score=-1, label="🔞 18+"),
    }),
}


DEFAULT_MEDIA_ATTR_SPECS = {
    "quality": FieldSpec(values={
        "4K": ValueSpec(score=500000, label="🟣 4K"),
        "1440p": ValueSpec(score=400000, label="🟢 1440p"),
        "1080p": ValueSpec(score=300000, label="🟢 1080p"),
        "720p": ValueSpec(score=200000, label="🟡 720p"),
        "480p": ValueSpec(score=100000, label="🔴 480p"),
        "360p": ValueSpec(label="🔴 360p"),
    }),
    "codec": FieldSpec(values={
        "AV1": ValueSpec(score=1),
        "HEVC": ValueSpec(score=1),
        "H264": ValueSpec(),
    }),
    "hdr": FieldSpec(values={
        "DV": ValueSpec(score=20000, label="✨ DV"),
        "HDR10+": ValueSpec(score=15000, label="✨ HDR10+"),
        "HDR10": ValueSpec(score=10000, label="✨ HDR10"),
        "HDR": ValueSpec(score=5000, label="✨ HDR"),
    }),
    "edition": FieldSpec(values={
        "directors_cut": ValueSpec(score=4, msgid="edition.directors_cut"),
        "extended": ValueSpec(score=3, msgid="edition.extended"),
        "uncut": ValueSpec(score=2, msgid="edition.uncut"),
        "imax": ValueSpec(score=1, label="📀 IMAX"),
        "theatrical": ValueSpec(msgid="edition.theatrical"),
        "combined": ValueSpec(msgid="edition.combined"),
        "3d": ValueSpec(score=-50000, label="3D"),
    }),
}


DEFAULT_IGNORED_PATTERNS = (
    r"\b(?:SDR|SUB|BDRip|[РP] - )\b",
)


DEFAULT_TRACK_MARKERS = {
    "lang_ru": MarkerSpec(pattern=r"\b(?:RU|Rus|Рус\w*)\b", attrs={"lang": MarkerValueSpec(id="ru", anchored=True)}),
    "lang_uk": MarkerSpec(pattern=r"\b(?:UA|Ukr\w*|Укр\w*)\b", attrs={"lang": MarkerValueSpec(id="uk", anchored=True)}),
    "lang_en": MarkerSpec(pattern=r"\b(?:EN|Eng(?:lish)?)\b", attrs={"lang": MarkerValueSpec(id="en", anchored=True)}),
    "lang_de": MarkerSpec(pattern=r"\b(?:DE|Ger(?:man)?)\b", attrs={"lang": MarkerValueSpec(id="de", anchored=True)}),
    "lang_fr": MarkerSpec(pattern=r"\b(?:French|Francais|Fre)\b", attrs={"lang": MarkerValueSpec(id="fr", anchored=True)}),
    "lang_es": MarkerSpec(pattern=r"\b(?:Spanish|Espanol|Castellano|Spa)\b", attrs={"lang": MarkerValueSpec(id="es", anchored=True)}),
    "lang_it": MarkerSpec(pattern=r"\b(?:Italian|Italiano|Ita)\b", attrs={"lang": MarkerValueSpec(id="it", anchored=True)}),
    "lang_pt": MarkerSpec(pattern=r"\b(?:Portuguese|Portugues|Brazilian Portuguese|PT-BR|Por)\b", attrs={"lang": MarkerValueSpec(id="pt", anchored=True)}),
    "lang_nl": MarkerSpec(pattern=r"\b(?:Dutch|Nederlands|Dut)\b", attrs={"lang": MarkerValueSpec(id="nl", anchored=True)}),
    "lang_sv": MarkerSpec(pattern=r"\b(?:Swedish|Svenska|Swe)\b", attrs={"lang": MarkerValueSpec(id="sv", anchored=True)}),
    "lang_no": MarkerSpec(pattern=r"\b(?:Norwegian|Norsk|Nor)\b", attrs={"lang": MarkerValueSpec(id="no", anchored=True)}),
    "lang_da": MarkerSpec(pattern=r"\b(?:Danish|Dansk|Dan)\b", attrs={"lang": MarkerValueSpec(id="da", anchored=True)}),
    "lang_fi": MarkerSpec(pattern=r"\b(?:Finnish|Suomi|Fin)\b", attrs={"lang": MarkerValueSpec(id="fi", anchored=True)}),
    "lang_pl": MarkerSpec(pattern=r"\b(?:Polish|Polski|Pol)\b", attrs={"lang": MarkerValueSpec(id="pl", anchored=True)}),
    "lang_cs": MarkerSpec(pattern=r"\b(?:Czech|Cestina|Cesky|Cze)\b", attrs={"lang": MarkerValueSpec(id="cs", anchored=True)}),
    "lang_hu": MarkerSpec(pattern=r"\b(?:Hungarian|Magyar|Hun)\b", attrs={"lang": MarkerValueSpec(id="hu", anchored=True)}),
    "lang_ro": MarkerSpec(pattern=r"\b(?:Romanian|Romana|Rum|Ron)\b", attrs={"lang": MarkerValueSpec(id="ro", anchored=True)}),
    "lang_el": MarkerSpec(pattern=r"\b(?:Greek|Ellinika)\b", attrs={"lang": MarkerValueSpec(id="el", anchored=True)}),
    "lang_zh": MarkerSpec(pattern=r"\b(?:Chinese|Mandarin|Cantonese|Chi)\b", attrs={"lang": MarkerValueSpec(id="zh", anchored=True)}),
    "lang_ja": MarkerSpec(pattern=r"\b(?:Japanese|Nihongo|Jpn|Jap)\b", attrs={"lang": MarkerValueSpec(id="ja", anchored=True)}),
    "lang_ko": MarkerSpec(pattern=r"\b(?:Korean|Hanguk(?:eo)?|Kor)\b", attrs={"lang": MarkerValueSpec(id="ko", anchored=True)}),
    "lang_hi": MarkerSpec(pattern=r"\b(?:Hindi|Hin)\b", attrs={"lang": MarkerValueSpec(id="hi", anchored=True)}),
    "lang_th": MarkerSpec(pattern=r"\b(?:Thai|Tha)\b", attrs={"lang": MarkerValueSpec(id="th", anchored=True)}),
    "lang_id": MarkerSpec(pattern=r"\b(?:Indonesian|Bahasa\s*Indonesia|Ind)\b", attrs={"lang": MarkerValueSpec(id="id", anchored=True)}),
    "lang_vi": MarkerSpec(pattern=r"\b(?:Vietnamese|Tieng\s*Viet|Vie)\b", attrs={"lang": MarkerValueSpec(id="vi", anchored=True)}),
    "lang_ms": MarkerSpec(pattern=r"\b(?:Malay|Bahasa\s*Melayu|May|Msa)\b", attrs={"lang": MarkerValueSpec(id="ms", anchored=True)}),
    "voice_dub_uk": MarkerSpec(pattern=r"\bДубльован\w*\b", attrs={"voice_type": MarkerValueSpec(id="DUB", anchored=True), "lang": MarkerValueSpec(id="uk")}),
    "voice_dub": MarkerSpec(pattern=r"\b(?:DUB|Дублир\w*|Дубляж)\b", attrs={"voice_type": MarkerValueSpec(id="DUB", anchored=True)}),
    "voice_mvo": MarkerSpec(pattern=r"\b(?:MVO|Многоголос\w*)\b", attrs={"voice_type": MarkerValueSpec(id="MVO", anchored=True)}),
    "voice_dvo": MarkerSpec(pattern=r"\b(?:DVO|Двухголос\w*)\b", attrs={"voice_type": MarkerValueSpec(id="DVO", anchored=True)}),
    "voice_avo": MarkerSpec(pattern=r"\b(?:AVO|VO|Одноголос\w*)\b", attrs={"voice_type": MarkerValueSpec(id="AVO", anchored=True)}),
    "voice_original": MarkerSpec(pattern=r"\b(?:Оригинал\w*|Original|Orig)\b", attrs={"voice_type": MarkerValueSpec(id="OG", anchored=True)}),
    "studio_pifagor": MarkerSpec(
        pattern=r"\bПифагор\b",
        attrs={
            "studio": MarkerValueSpec(id="Пифагор", score=28, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_mosfilm": MarkerSpec(
        pattern=r"\bМосфильм(?:[\s-]*Мастер)?\b",
        attrs={
            "studio": MarkerValueSpec(id="Мосфильм", score=30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_nevafilm": MarkerSpec(
        pattern=r"\b(?:Невафильм|Nevafilm)\b",
        attrs={
            "studio": MarkerValueSpec(id="Невафильм", score=30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_kirillitsa": MarkerSpec(
        pattern=r"\bКириллица\b",
        attrs={
            "studio": MarkerValueSpec(id="Кириллица", score=24, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_true_dubbing": MarkerSpec(
        pattern=r"\bTrue\s*Dubbing\b",
        attrs={
            "studio": MarkerValueSpec(id="True Dubbing", score=24, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_kiparis": MarkerSpec(
        pattern=r"\bКипарис\b",
        attrs={
            "studio": MarkerValueSpec(id="Кипарис", score=22, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_sdi_media": MarkerSpec(
        pattern=r"\b(?:Blackbird\s*Sound|SDI\s*Media(?:\s*Russia)?|Iyuno[\s-]*(?:SDI(?:\s*Group)?(?:\s*(?:Latvia|Russia|Moscow))?|Russia|Moscow))\b",
        attrs={
            "studio": MarkerValueSpec(id="SDI Media", score=22, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_sv_dubl": MarkerSpec(
        pattern=r"\bСВ[\s-]*Дубль\b",
        attrs={
            "studio": MarkerValueSpec(id="СВ-Дубль", score=22, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_rhs": MarkerSpec(
        pattern=r"\b(?:RHS|Red\s*Head\s*Sound)\b",
        attrs={
            "studio": MarkerValueSpec(id="Red Head Sound", score=20, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_lostfilm": MarkerSpec(
        pattern=r"\bLostFilm\b",
        attrs={
            "studio": MarkerValueSpec(id="LostFilm", score=20, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_tvshows": MarkerSpec(
        pattern=r"\bTVShows\b",
        attrs={
            "studio": MarkerValueSpec(id="TVShows", score=16, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_newstudio": MarkerSpec(
        pattern=r"\bNewStudio\b",
        attrs={
            "studio": MarkerValueSpec(id="NewStudio", score=16, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_kubik_v_kube": MarkerSpec(
        pattern=r"\bКубик\s*[Вв]\s*Кубе\b",
        attrs={
            "studio": MarkerValueSpec(id="Кубик в Кубе", score=14, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DVO", confidence=-10),
        },
    ),
    "studio_alexfilm": MarkerSpec(
        pattern=r"\bAlexFilm\b",
        attrs={
            "studio": MarkerValueSpec(id="AlexFilm", score=14, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_jaskier": MarkerSpec(
        pattern=r"\bJaskier\b",
        attrs={
            "studio": MarkerValueSpec(id="Jaskier", score=14, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_baibako": MarkerSpec(
        pattern=r"\bBaibaKo\b",
        attrs={
            "studio": MarkerValueSpec(id="BaibaKo", score=12, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_kurazh_bambey": MarkerSpec(
        pattern=r"\bКураж[\s-]*Бамбей\b",
        attrs={
            "studio": MarkerValueSpec(id="Кураж-Бамбей", score=12, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="AVO", confidence=-10),
        },
    ),
    "studio_hdrezka": MarkerSpec(
        pattern=r"\bHDrezka\b",
        attrs={
            "studio": MarkerValueSpec(id="HDrezka", score=10, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_ideafilm": MarkerSpec(
        pattern=r"\bIdeaFilm\b",
        attrs={
            "studio": MarkerValueSpec(id="IdeaFilm", score=10, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_rudub": MarkerSpec(
        pattern=r"\bRuDub\b",
        attrs={
            "studio": MarkerValueSpec(id="RuDub", score=10, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_coldfilm": MarkerSpec(
        pattern=r"\bColdFilm\b",
        attrs={
            "studio": MarkerValueSpec(id="ColdFilm", score=6, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_omskbird": MarkerSpec(
        pattern=r"\bOmskBird\b",
        attrs={
            "studio": MarkerValueSpec(id="OmskBird", score=6, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_1winstudio": MarkerSpec(
        pattern=r"\b(?:1WinStudio|1W)\b",
        attrs={
            "studio": MarkerValueSpec(id="1WinStudio", score=-30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_dragon_money": MarkerSpec(
        pattern=r"\bDragon\s*Money\s*Studio\b",
        attrs={
            "studio": MarkerValueSpec(id="Dragon Money", score=-30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
        },
    ),
    "studio_le_prod": MarkerSpec(
        pattern=r"\bLE\s*-?Production\b",
        attrs={
            "studio": MarkerValueSpec(id="LE-Prod.", score=-30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
        },
    ),
    "studio_ultradox": MarkerSpec(
        pattern=r"\bUltradox\b",
        attrs={
            "studio": MarkerValueSpec(id="Ultradox", score=-30, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
        },
    ),
    "studio_reanimedia": MarkerSpec(
        pattern=r"\bReanimedia\b",
        attrs={
            "studio": MarkerValueSpec(id="Reanimedia", score=28, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_mc_entertainment": MarkerSpec(
        pattern=r"\bMC\s*Entertainment\b",
        attrs={
            "studio": MarkerValueSpec(id="MC Entertainment", score=20, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_force_media": MarkerSpec(
        pattern=r"\bForce\s*Media\b",
        attrs={
            "studio": MarkerValueSpec(id="Force Media", score=20, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_amber": MarkerSpec(
        pattern=r"\bAmber\b",
        attrs={
            "studio": MarkerValueSpec(id="Amber", score=15, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_kansai": MarkerSpec(
        pattern=r"\bKansai\b",
        attrs={
            "studio": MarkerValueSpec(id="Kansai", score=15, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_studioband": MarkerSpec(
        pattern=r"\b(?:Studio\s*Band|Студійна\s*Банда)\b",
        attrs={
            "studio": MarkerValueSpec(id="StudioBand", score=15, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_shiza_project": MarkerSpec(
        pattern=r"\bShiza\s*Project\b",
        attrs={
            "studio": MarkerValueSpec(id="Shiza Project", score=13, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_anidub": MarkerSpec(
        pattern=r"\bAniDub\b",
        attrs={
            "studio": MarkerValueSpec(id="AniDub", score=12, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_anilibria": MarkerSpec(
        pattern=r"\bAni[Ll]ibria\b",
        attrs={
            "studio": MarkerValueSpec(id="AniLibria", score=12, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_jam": MarkerSpec(
        pattern=r"\bJ(?:AM|am)\b",
        attrs={
            "studio": MarkerValueSpec(id="JAM", score=8, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="DVO", confidence=-10),
        },
    ),
    "studio_dream_cast": MarkerSpec(
        pattern=r"\bDream\s*Cast\b",
        attrs={
            "studio": MarkerValueSpec(id="Dream Cast", score=8, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="MVO", confidence=-10),
        },
    ),
    "studio_persona99": MarkerSpec(
        pattern=r"\bPersona\s*99\b",
        attrs={
            "studio": MarkerValueSpec(id="Persona99", score=6, anchored=True),
            "lang": MarkerValueSpec(id="ru", confidence=-10),
            "voice_type": MarkerValueSpec(id="AVO", confidence=-10),
        },
    ),
    "studio_postmodern": MarkerSpec(
        pattern=r"\bPostModern\b",
        attrs={
            "studio": MarkerValueSpec(id="PostModern", score=20, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "studio_1plus1": MarkerSpec(
        pattern=r"\b1\+1\b",
        attrs={
            "studio": MarkerValueSpec(id="1+1", score=14, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "studio_ne_zupynyay_prod": MarkerSpec(
        pattern=r"\bНеЗупиняйПрод\b\.?",
        attrs={
            "studio": MarkerValueSpec(id="НеЗупиняйПрод", score=6, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "studio_uateam": MarkerSpec(
        pattern=r"\bUA[-_]?Team\b",
        attrs={
            "studio": MarkerValueSpec(id="UATeam", score=6, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "studio_dniprofilm": MarkerSpec(
        pattern=r"\bDniproFilm\b",
        attrs={
            "studio": MarkerValueSpec(id="DniproFilm", score=4, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "studio_amanogawa": MarkerSpec(
        pattern=r"\bAmanogawa\b",
        attrs={
            "studio": MarkerValueSpec(id="Amanogawa", score=4, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "studio_inaridub": MarkerSpec(
        pattern=r"\bInariDub\b",
        attrs={
            "studio": MarkerValueSpec(id="InariDub", score=4, anchored=True),
            "lang": MarkerValueSpec(id="uk", confidence=-10),
        },
    ),
    "commentary": MarkerSpec(pattern=r"\b(?:Комментарии|Commentary)\b", attrs={"commentary": MarkerValueSpec(id="commentary", anchored=True)}),
    "official": MarkerSpec(
        pattern=r"\b(?:Blu-ray|Официальный|Лицензия|BD[\s-]*C(?:EE|ee))\b",
        attrs={
            "official": MarkerValueSpec(id="official", anchored=True),
            "voice_type": MarkerValueSpec(id="DUB"),
        },
    ),
    "unofficial": MarkerSpec(
        pattern=r"\bНеофициальный\b",
        attrs={
            "official": MarkerValueSpec(id="unofficial", anchored=True),
            "voice_type": MarkerValueSpec(id="DUB"),
        },
    ),
    "network_hbo": MarkerSpec(
        pattern=r"\bHBO\b",
        attrs={
            "network": MarkerValueSpec(id="HBO", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_netflix": MarkerSpec(
        pattern=r"\bNetflix\b",
        attrs={
            "network": MarkerValueSpec(id="Netflix", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_amazon": MarkerSpec(
        pattern=r"\bAmazon\b",
        attrs={
            "network": MarkerValueSpec(id="Amazon", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_apple_tv": MarkerSpec(
        pattern=r"\bApple\s*TV\+?\b",
        attrs={
            "network": MarkerValueSpec(id="Apple TV+", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_disney": MarkerSpec(
        pattern=r"\bDisney\s*\+\b",
        attrs={
            "network": MarkerValueSpec(id="Disney+", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_hulu": MarkerSpec(
        pattern=r"\bHulu\b",
        attrs={
            "network": MarkerValueSpec(id="Hulu", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_crunchyroll": MarkerSpec(
        pattern=r"\bCrunchyroll\b",
        attrs={
            "network": MarkerValueSpec(id="Crunchyroll", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "network_amedia": MarkerSpec(
        pattern=r"\bAmedia\b",
        attrs={
            "network": MarkerValueSpec(id="Amedia", hidden=True, anchored=True),
            "official": MarkerValueSpec(id="official"),
        },
    ),
    "audio_format_atmos": MarkerSpec(pattern=r"\bAtmos\b", attrs={"audio_format": MarkerValueSpec(id="Atmos", anchored=True)}),
    "audio_format_truehd": MarkerSpec(pattern=r"\bTrueHD\b", attrs={"audio_format": MarkerValueSpec(id="TrueHD", anchored=True)}),
    "audio_format_dtshd": MarkerSpec(pattern=r"\bDTS-HD\b", attrs={"audio_format": MarkerValueSpec(id="DTS-HD", anchored=True)}),
    "audio_format_dts": MarkerSpec(pattern=r"\bDTS\b", attrs={"audio_format": MarkerValueSpec(id="DTS", anchored=True)}),
    "audio_format_ac3": MarkerSpec(pattern=r"\bAC3\b", attrs={"audio_format": MarkerValueSpec(id="AC3", anchored=True)}),
    "audio_format_aac": MarkerSpec(pattern=r"\bAAC\b", attrs={"audio_format": MarkerValueSpec(id="AAC", anchored=True)}),
    "audio_note_clean": MarkerSpec(
        pattern=r"\b(?:Чистый\s*звук|Line)\b",
        attrs={
            "audio_note": MarkerValueSpec(id="clean", anchored=True),
            "voice_type": MarkerValueSpec(id="DUB", confidence=-10),
        },
    ),
    "ads": MarkerSpec(pattern=r"\b(?:AD|[Рр]еклама)\b", attrs={"ads": MarkerValueSpec(id="ads", anchored=True)}),
    "mature_18": MarkerSpec(pattern=r"\b18\+\b", attrs={"mature": MarkerValueSpec(id="18+", anchored=True)}),
}
DEFAULT_MEDIA_MARKERS = {
    "edition_directors_cut": MarkerSpec(pattern=r"\b(?:Режисс[её]рск\w*(?:\s+верси\w*)?|Director'?s?\s*Cut)\b", attrs={"edition": MarkerValueSpec(id="directors_cut")}),
    "edition_extended": MarkerSpec(pattern=r"\b(?:Расширенн\w*(?:\s+верси\w*)?|Extended(?:\s*(?:Edition|Cut|Version))?)\b", attrs={"edition": MarkerValueSpec(id="extended")}),
    "edition_theatrical": MarkerSpec(pattern=r"\b(?:Театральн\w*(?:\s+верси\w*)?|Theatrical(?:\s*Cut)?)\b", attrs={"edition": MarkerValueSpec(id="theatrical")}),
    "edition_uncut": MarkerSpec(pattern=r"\bUncut\b", attrs={"edition": MarkerValueSpec(id="uncut")}),
    "edition_imax": MarkerSpec(pattern=r"\bIMAX(?:\s*Edition)?\b", attrs={"edition": MarkerValueSpec(id="imax")}),
    "edition_3d": MarkerSpec(pattern=r"\b3D\b", attrs={"edition": MarkerValueSpec(id="3d")}),
    "quality_4k": MarkerSpec(pattern=r"\b(?:4K|2160p?)\b", attrs={"quality": MarkerValueSpec(id="4K")}),
    "quality_1440p": MarkerSpec(pattern=r"\b(?:1440p?|2K)\b", attrs={"quality": MarkerValueSpec(id="1440p")}),
    "quality_1080p": MarkerSpec(pattern=r"\b1080p?\b", attrs={"quality": MarkerValueSpec(id="1080p")}),
    "quality_720p": MarkerSpec(pattern=r"\b720p?\b", attrs={"quality": MarkerValueSpec(id="720p")}),
    "quality_480p": MarkerSpec(pattern=r"\b480p?\b", attrs={"quality": MarkerValueSpec(id="480p")}),
    "quality_360p": MarkerSpec(pattern=r"\b360p?\b", attrs={"quality": MarkerValueSpec(id="360p")}),
    "hdr_dv": MarkerSpec(pattern=r"\b(?:Dolby\s*Vision|DV)\b", attrs={"hdr": MarkerValueSpec(id="DV")}),
    "hdr_hdr10_plus": MarkerSpec(pattern=r"\bHDR10\+", attrs={"hdr": MarkerValueSpec(id="HDR10+")}),
    "hdr_hdr10": MarkerSpec(pattern=r"\bHDR10(?!\+)\b", attrs={"hdr": MarkerValueSpec(id="HDR10")}),
    "hdr_hdr": MarkerSpec(pattern=r"\bHDR\b", attrs={"hdr": MarkerValueSpec(id="HDR")}),
    "codec_av1": MarkerSpec(pattern=r"\bAV1\b", attrs={"codec": MarkerValueSpec(id="AV1")}),
    "codec_hevc": MarkerSpec(pattern=r"\b(?:HEVC|H\.?265)\b", attrs={"codec": MarkerValueSpec(id="HEVC")}),
    "codec_h264": MarkerSpec(pattern=r"\bH\.?264\b", attrs={"codec": MarkerValueSpec(id="H264")}),
}


DEFAULT_PARSING_SPECS = ParsingSpecs(
    attrs={
        **DEFAULT_TRACK_ATTR_SPECS,
        **DEFAULT_MEDIA_ATTR_SPECS,
    },
    markers={
        Track.PARSING_GROUP: DEFAULT_TRACK_MARKERS,
        Media.PARSING_GROUP: DEFAULT_MEDIA_MARKERS,
    },
    ignored_patterns=DEFAULT_IGNORED_PATTERNS,
)
