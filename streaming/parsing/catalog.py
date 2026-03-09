import re

from languages import LangCode

from .core import ParserProfile, ParserRules
from .models import MediaMarker, TrackMarker
from .registry import Attr, Marker, OrgAttr, TrackAttr
from .schema import MediaSchema, OrgSchema, TrackSchema
from .values import OrgKind

IGNORED_PATTERNS = (
    re.compile(r"\b(?:SDR|SUB|BDRip|[РP] - )\b", re.I),
)

Studio = OrgAttr("studio", kind=OrgKind.STUDIO)
Network = OrgAttr("network", kind=OrgKind.NETWORK)

Lang: TrackAttr[LangCode] = TrackAttr("lang")
Lang.add("ru", score=3000)
Lang.add("uk", score=2000)
Lang.add("en", score=1000)
Lang.add("de")
Lang.add("fr")
Lang.add("es")
Lang.add("it")
Lang.add("pt")
Lang.add("nl")
Lang.add("sv")
Lang.add("no")
Lang.add("da")
Lang.add("fi")
Lang.add("pl")
Lang.add("cs")
Lang.add("hu")
Lang.add("ro")
Lang.add("el")
Lang.add("zh")
Lang.add("ja")
Lang.add("ko")
Lang.add("hi")
Lang.add("th")
Lang.add("id")
Lang.add("vi")
Lang.add("ms")

VoiceType = TrackAttr("voice_type")
VoiceType.add("DUB", score=70, label="DUB")
VoiceType.add("MVO", score=30, label="MVO")
VoiceType.add("DVO", label="DVO")
VoiceType.add("AVO", score=-10, label="AVO")
VoiceType.add("OG", score=-40, label="OG")

Official = TrackAttr("official")
Official.add("official", score=30, msgid="official.official")
Official.add("unofficial", msgid="official.unofficial")

AudioFormat = TrackAttr("audio_format")
AudioFormat.add("Atmos", score=20, label="🎵 Atmos")
AudioFormat.add("TrueHD", score=15, label="🎵 TrueHD")
AudioFormat.add("DTS-HD", score=12, label="🎵 DTS-HD")
AudioFormat.add("DTS", score=10, label="🎵 DTS")
AudioFormat.add("AC3", score=0, hidden=True)
AudioFormat.add("AAC", hidden=True)

AudioNote = TrackAttr("audio_note")
AudioNote.add("clean", score=-10, msgid="audio_note.clean")

Commentary = TrackAttr("commentary")
Commentary.add("commentary", score=-50, msgid="commentary.commentary")

Ads = TrackAttr("ads")
Ads.add("ads", score=-50000, msgid="ads.ads")

Mature = TrackAttr("mature")
Mature.add("18+", score=-1, label="🔞 18+")

Quality = Attr("quality")
Quality.add("4K", score=500000, label="🟣 4K")
Quality.add("1440p", score=400000, label="🟢 1440p")
Quality.add("1080p", score=300000, label="🟢 1080p")
Quality.add("720p", score=200000, label="🟡 720p")
Quality.add("480p", score=100000, label="🔴 480p")
Quality.add("360p", label="🔴 360p")

Codec = Attr("codec")
Codec.add("AV1", score=1)
Codec.add("HEVC", score=1)
Codec.add("H264")

HDR = Attr("hdr")
HDR.add("DV", score=20000, label="✨ DV")
HDR.add("HDR10+", score=15000, label="✨ HDR10+")
HDR.add("HDR10", score=10000, label="✨ HDR10")
HDR.add("HDR", score=5000, label="✨ HDR")

Edition = Attr("edition")
Edition.add("directors_cut", score=4, msgid="edition.directors_cut")
Edition.add("extended", score=3, msgid="edition.extended")
Edition.add("uncut", score=2, msgid="edition.uncut")
Edition.add("imax", score=1, label="📀 IMAX")
Edition.add("theatrical", msgid="edition.theatrical")
Edition.add("combined", msgid="edition.combined")
Edition.add("3d", score=-50000, label="3D")

TRACK_MARKERS: list[TrackMarker] = [
    # Lang
    Marker(r"\b(?:RU|Rus|Рус\w*)\b", lang=Lang["ru"].anchor()),
    Marker(r"\b(?:UA|Ukr\w*|Укр\w*)\b", lang=Lang["uk"].anchor()),
    Marker(r"\b(?:EN|Eng(?:lish)?)\b", lang=Lang["en"].anchor()),
    Marker(r"\b(?:DE|Ger(?:man)?)\b", lang=Lang["de"].anchor()),
    Marker(r"\b(?:French|Francais|Fre)\b", lang=Lang["fr"].anchor()),
    Marker(r"\b(?:Spanish|Espanol|Castellano|Spa)\b", lang=Lang["es"].anchor()),
    Marker(r"\b(?:Italian|Italiano|Ita)\b", lang=Lang["it"].anchor()),
    Marker(r"\b(?:Portuguese|Portugues|Brazilian Portuguese|PT-BR|Por)\b", lang=Lang["pt"].anchor()),
    Marker(r"\b(?:Dutch|Nederlands|Dut)\b", lang=Lang["nl"].anchor()),
    Marker(r"\b(?:Swedish|Svenska|Swe)\b", lang=Lang["sv"].anchor()),
    Marker(r"\b(?:Norwegian|Norsk|Nor)\b", lang=Lang["no"].anchor()),
    Marker(r"\b(?:Danish|Dansk|Dan)\b", lang=Lang["da"].anchor()),
    Marker(r"\b(?:Finnish|Suomi|Fin)\b", lang=Lang["fi"].anchor()),
    Marker(r"\b(?:Polish|Polski|Pol)\b", lang=Lang["pl"].anchor()),
    Marker(r"\b(?:Czech|Cestina|Cesky|Cze)\b", lang=Lang["cs"].anchor()),
    Marker(r"\b(?:Hungarian|Magyar|Hun)\b", lang=Lang["hu"].anchor()),
    Marker(r"\b(?:Romanian|Romana|Rum|Ron)\b", lang=Lang["ro"].anchor()),
    Marker(r"\b(?:Greek|Ellinika)\b", lang=Lang["el"].anchor()),
    Marker(r"\b(?:Chinese|Mandarin|Cantonese|Chi)\b", lang=Lang["zh"].anchor()),
    Marker(r"\b(?:Japanese|Nihongo|Jpn|Jap)\b", lang=Lang["ja"].anchor()),
    Marker(r"\b(?:Korean|Hanguk(?:eo)?|Kor)\b", lang=Lang["ko"].anchor()),
    Marker(r"\b(?:Hindi|Hin)\b", lang=Lang["hi"].anchor()),
    Marker(r"\b(?:Thai|Tha)\b", lang=Lang["th"].anchor()),
    Marker(r"\b(?:Indonesian|Bahasa\s*Indonesia|Ind)\b", lang=Lang["id"].anchor()),
    Marker(r"\b(?:Vietnamese|Tieng\s*Viet|Vie)\b", lang=Lang["vi"].anchor()),
    Marker(r"\b(?:Malay|Bahasa\s*Melayu|May|Msa)\b", lang=Lang["ms"].anchor()),

    # Voice type
    Marker(r"\bДубльован\w*\b", voice_type=VoiceType["DUB"].anchor(), lang=Lang["uk"]),
    Marker(r"\b(?:DUB|Дублир\w*|Дубляж)\b", voice_type=VoiceType["DUB"].anchor()),
    Marker(r"\b(?:MVO|Многоголос\w*)\b", voice_type=VoiceType["MVO"].anchor()),
    Marker(r"\b(?:DVO|Двухголос\w*)\b", voice_type=VoiceType["DVO"].anchor()),
    Marker(r"\b(?:AVO|VO|Одноголос\w*)\b", voice_type=VoiceType["AVO"].anchor()),
    Marker(r"\b(?:Оригинал\w*|Original|Orig)\b", voice_type=VoiceType["OG"].anchor()),

    # Russian: official / licensed studios
    Marker(r"\bПифагор\b", studio=Studio.add("Пифагор", score=28).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(r"\bМосфильм(?:[\s-]*Мастер)?\b", studio=Studio.add("Мосфильм", score=30).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(r"\b(?:Невафильм|Nevafilm)\b", studio=Studio.add("Невафильм", score=30).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(r"\bКириллица\b", studio=Studio.add("Кириллица", score=24).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bTrue\s*Dubbing\b", studio=Studio.add("True Dubbing", score=24).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(r"\bКипарис\b", studio=Studio.add("Кипарис", score=22).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(
        r"\b(?:Blackbird\s*Sound|SDI\s*Media(?:\s*Russia)?|Iyuno[\s-]*(?:SDI(?:\s*Group)?(?:\s*(?:Latvia|Russia|Moscow))?|Russia|Moscow))\b",
        studio=Studio.add("SDI Media", score=22).anchor(),
        lang=-Lang["ru"],
        voice_type=-VoiceType["MVO"],
    ),
    Marker(r"\bСВ[\s-]*Дубль\b", studio=Studio.add("СВ-Дубль", score=22).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\b(?:RHS|Red\s*Head\s*Sound)\b", studio=Studio.add("Red Head Sound", score=20).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),

    # Russian: professional
    Marker(r"\bLostFilm\b", studio=Studio.add("LostFilm", score=20).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bTVShows\b", studio=Studio.add("TVShows", score=16).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bNewStudio\b", studio=Studio.add("NewStudio", score=16).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bКубик\s*[Вв]\s*Кубе\b", studio=Studio.add("Кубик в Кубе", score=14).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DVO"]),
    Marker(r"\bAlexFilm\b", studio=Studio.add("AlexFilm", score=14).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bJaskier\b", studio=Studio.add("Jaskier", score=14).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bBaibaKo\b", studio=Studio.add("BaibaKo", score=12).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bКураж[\s-]*Бамбей\b", studio=Studio.add("Кураж-Бамбей", score=12).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["AVO"]),
    Marker(r"\bHDrezka\b", studio=Studio.add("HDrezka", score=10).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bIdeaFilm\b", studio=Studio.add("IdeaFilm", score=10).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bRuDub\b", studio=Studio.add("RuDub", score=10).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bColdFilm\b", studio=Studio.add("ColdFilm", score=6).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bOmskBird\b", studio=Studio.add("OmskBird", score=6).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),

    # Russian: casino spam
    Marker(r"\b(?:1WinStudio|1W)\b", studio=Studio.add("1WinStudio", score=-30).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bDragon\s*Money\s*Studio\b", studio=Studio.add("Dragon Money", score=-30).anchor(), lang=-Lang["ru"]),
    Marker(r"\bLE\s*-?Production\b", studio=Studio.add("LE-Prod.", score=-30).anchor(), lang=-Lang["ru"]),
    Marker(r"\bUltradox\b", studio=Studio.add("Ultradox", score=-30).anchor(), lang=-Lang["ru"]),

    # Russian: anime
    Marker(r"\bReanimedia\b", studio=Studio.add("Reanimedia", score=28).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DUB"]),
    Marker(r"\bMC\s*Entertainment\b", studio=Studio.add("MC Entertainment", score=20).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bForce\s*Media\b", studio=Studio.add("Force Media", score=20).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bAmber\b", studio=Studio.add("Amber", score=15).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bKansai\b", studio=Studio.add("Kansai", score=15).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\b(?:Studio\s*Band|Студійна\s*Банда)\b", studio=Studio.add("StudioBand", score=15).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bShiza\s*Project\b", studio=Studio.add("Shiza Project", score=13).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bAniDub\b", studio=Studio.add("AniDub", score=12).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bAni[Ll]ibria\b", studio=Studio.add("AniLibria", score=12).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bJ(?:AM|am)\b", studio=Studio.add("JAM", score=8).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["DVO"]),
    Marker(r"\bDream\s*Cast\b", studio=Studio.add("Dream Cast", score=8).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["MVO"]),
    Marker(r"\bPersona\s*99\b", studio=Studio.add("Persona99", score=6).anchor(), lang=-Lang["ru"], voice_type=-VoiceType["AVO"]),

    # Ukrainian studios
    Marker(r"\bPostModern\b", studio=Studio.add("PostModern", score=20).anchor(), lang=-Lang["uk"], voice_type=-VoiceType["DUB"]),
    Marker(r"\b1\+1\b", studio=Studio.add("1+1", score=14).anchor(), lang=-Lang["uk"]),
    Marker(r"\bНеЗупиняйПрод\b\.?", studio=Studio.add("НеЗупиняйПрод", score=6).anchor(), lang=-Lang["uk"]),
    Marker(r"\bUA[-_]?Team\b", studio=Studio.add("UATeam", score=6).anchor(), lang=-Lang["uk"]),
    Marker(r"\bDniproFilm\b", studio=Studio.add("DniproFilm", score=4).anchor(), lang=-Lang["uk"]),
    Marker(r"\bAmanogawa\b", studio=Studio.add("Amanogawa", score=4).anchor(), lang=-Lang["uk"]),
    Marker(r"\bInariDub\b", studio=Studio.add("InariDub", score=4).anchor(), lang=-Lang["uk"]),

    # Misc
    Marker(r"\b(?:Комментарии|Commentary)\b", commentary=Commentary["commentary"].anchor()),
    Marker(r"\b(?:Blu-ray|Официальный|Лицензия|BD[\s-]*C(?:EE|ee))\b", official=Official["official"].anchor(), voice_type=VoiceType["DUB"]),
    Marker(r"\bНеофициальный\b", official=Official["unofficial"].anchor(), voice_type=VoiceType["DUB"]),

    # Network
    Marker(r"\bHBO\b", network=Network.add("HBO", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bNetflix\b", network=Network.add("Netflix", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bAmazon\b", network=Network.add("Amazon", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bApple\s*TV\+?\b", network=Network.add("Apple TV+", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bDisney\s*\+\b", network=Network.add("Disney+", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bHulu\b", network=Network.add("Hulu", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bCrunchyroll\b", network=Network.add("Crunchyroll", hidden=True).anchor(), official=Official["official"]),
    Marker(r"\bAmedia\b", network=Network.add("Amedia", hidden=True).anchor(), official=Official["official"]),

    # Audio format
    Marker(r"\bAtmos\b", audio_format=AudioFormat["Atmos"].anchor()),
    Marker(r"\bTrueHD\b", audio_format=AudioFormat["TrueHD"].anchor()),
    Marker(r"\bDTS-HD\b", audio_format=AudioFormat["DTS-HD"].anchor()),
    Marker(r"\bDTS\b", audio_format=AudioFormat["DTS"].anchor()),
    Marker(r"\bAC3\b", audio_format=AudioFormat["AC3"].anchor()),
    Marker(r"\bAAC\b", audio_format=AudioFormat["AAC"].anchor()),

    # Audio tags
    Marker(r"\b(?:Чистый\s*звук|Line)\b", audio_note=AudioNote["clean"].anchor(), voice_type=-VoiceType["DUB"]),
    Marker(r"\b(?:AD|[Рр]еклама)\b", ads=Ads["ads"].anchor()),
    Marker(r"\b18\+\b", mature=Mature["18+"].anchor()),
]

MEDIA_MARKERS: list[MediaMarker] = [
    Marker(r"\b(?:Режиссерск\w*(?:\s+верси\w*)?|Director'?s?\s*Cut)\b", edition=Edition["directors_cut"]),
    Marker(r"\b(?:Расширенн\w*(?:\s+верси\w*)?|Extended(?:\s*(?:Edition|Cut|Version))?)\b", edition=Edition["extended"]),
    Marker(r"\b(?:Театральн\w*(?:\s+верси\w*)?|Theatrical(?:\s*Cut)?)\b", edition=Edition["theatrical"]),
    Marker(r"\bUncut\b", edition=Edition["uncut"]),
    Marker(r"\bIMAX(?:\s*Edition)?\b", edition=Edition["imax"]),
    Marker(r"\b3D\b", edition=Edition["3d"]),

    Marker(r"\b(?:4K|2160p?)\b", quality=Quality["4K"]),
    Marker(r"\b(?:1440p?|2K)\b", quality=Quality["1440p"]),
    Marker(r"\b1080p?\b", quality=Quality["1080p"]),
    Marker(r"\b720p?\b", quality=Quality["720p"]),
    Marker(r"\b480p?\b", quality=Quality["480p"]),
    Marker(r"\b360p?\b", quality=Quality["360p"]),

    Marker(r"\b(?:Dolby\s*Vision|DV)\b", hdr=HDR["DV"]),
    Marker(r"\bHDR10\+", hdr=HDR["HDR10+"]),
    Marker(r"\bHDR10(?!\+)\b", hdr=HDR["HDR10"]),
    Marker(r"\bHDR\b", hdr=HDR["HDR"]),

    Marker(r"\bAV1\b", codec=Codec["AV1"]),
    Marker(r"\b(?:HEVC|H\.?265)\b", codec=Codec["HEVC"]),
    Marker(r"\bH\.?264\b", codec=Codec["H264"]),
]

default_profile = ParserProfile(
    media=MediaSchema(
        track=TrackSchema(
            lang=Lang,
            voice_type=VoiceType,
            orgs=OrgSchema(studio=Studio, network=Network),
            official=Official,
            audio_format=AudioFormat,
            audio_note=AudioNote,
            commentary=Commentary,
            ads=Ads,
            mature=Mature,
        ),
        quality=Quality,
        codec=Codec,
        hdr=HDR,
        edition=Edition,
    ),
    rules=ParserRules(
        track_markers=tuple(TRACK_MARKERS),
        media_markers=tuple(MEDIA_MARKERS),
        ignored_patterns=IGNORED_PATTERNS,
    ),
)
