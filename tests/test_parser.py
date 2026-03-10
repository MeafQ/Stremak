from dataclasses import dataclass

import pytest

from streaming.filmix.core import Filmix, FilmixPrivate


def _key(attr):
    return attr.id if attr else None


def _org_ids(track):
    return tuple(org.id for org in track.orgs)


@dataclass(frozen=True, slots=True)
class ExpectedTrack:
    lang: str | None
    voice_type: str | None
    orgs: tuple[str, ...] = ()


def expect_track(lang: str | None, voice_type: str | None, *orgs: str) -> ExpectedTrack:
    return ExpectedTrack(lang=lang, voice_type=voice_type, orgs=orgs)


VOICEOVER_CASES = [
    pytest.param(
        "Дубляж [1080+, ru, SC Produb, BDRip]",
        [expect_track("ru", "DUB", "SC Produb")],
        {"quality": "1080p"},
        id="dub-sc-produb-1080",
    ),
    pytest.param(
        "Дубляж [4K, SDR, ru, Red Head Sound]",
        [expect_track("ru", "DUB", "Red Head Sound")],
        {"quality": "4K"},
        id="dub-rhs-4k",
    ),
    pytest.param(
        "MVO [4K, SDR, Ukr, DniproFilm]",
        [expect_track("uk", "MVO", "DniproFilm")],
        {"quality": "4K"},
        id="mvo-uk-dniprofilm",
    ),
    pytest.param(
        "MVO [4K, SDR, ru, TVShows]",
        [expect_track("ru", "MVO", "TVShows")],
        {"quality": "4K"},
        id="mvo-tvshows-4k",
    ),
    pytest.param(
        "MVO [1080+, ru, LostFilm]",
        [expect_track("ru", "MVO", "LostFilm")],
        {"quality": "1080p"},
        id="mvo-lostfilm-1080",
    ),
    pytest.param(
        "Дубляж [Rus, Кириллица]",
        [expect_track("ru", "DUB", "Кириллица")],
        {},
        id="dub-kirillica",
    ),
    pytest.param(
        "Дубляж [Rus, Amedia]",
        [expect_track("ru", "DUB", "Amedia")],
        {},
        id="dub-amedia",
    ),
    pytest.param(
        "MVO [1080+, ru, R5, BDRip]",
        [expect_track("ru", "MVO", "R5")],
        {"quality": "1080p"},
        id="mvo-r5-1080",
    ),
    pytest.param(
        "Дубльований [Український]",
        [expect_track("uk", "DUB")],
        {},
        id="uk-dub-only",
    ),
    pytest.param(
        "Дубляж [4K, SDR, Ukr, LeDoyen]",
        [expect_track("uk", "DUB", "LeDoyen")],
        {"quality": "4K"},
        id="uk-dub-ledoyen-4k",
    ),
    pytest.param(
        "Дубляж [1080, Ukr, Amanogawa]",
        [expect_track("uk", "DUB", "Amanogawa")],
        {"quality": "1080p"},
        id="uk-dub-amanogawa-1080",
    ),
    pytest.param(
        "MVO [1080, Ukr, UATeam]",
        [expect_track("uk", "MVO", "UATeam")],
        {"quality": "1080p"},
        id="uk-mvo-uateam-1080",
    ),
    pytest.param(
        "Дублированный [HDR10+, 4K, +UA]",
        [expect_track("ru", "DUB"), expect_track("uk", "DUB")],
        {"hdr": "HDR10+", "quality": "4K"},
        id="ru-plus-ua-dub-hdr10-4k",
    ),
    pytest.param(
        "Дубляж [HDR10+, 4K, +UA]",
        [expect_track("ru", "DUB"), expect_track("uk", "DUB")],
        {"hdr": "HDR10+", "quality": "4K"},
        id="dub-plus-ua-hdr10-4k",
    ),
    pytest.param(
        "LostFilm",
        [expect_track("ru", "MVO", "LostFilm")],
        {},
        id="bare-lostfilm",
    ),
    pytest.param(
        "SDI Media",
        [expect_track("ru", "MVO", "SDI Media")],
        {},
        id="bare-sdi-media",
    ),
    pytest.param(
        "NewStudio",
        [expect_track("ru", "MVO", "NewStudio")],
        {},
        id="bare-newstudio",
    ),
    pytest.param(
        "ColdFilm",
        [expect_track("ru", "MVO", "ColdFilm")],
        {},
        id="bare-coldfilm",
    ),
    pytest.param(
        "BaibaKo [UKR]",
        [expect_track("uk", "MVO", "BaibaKo")],
        {},
        id="baibako-ukr",
    ),
    pytest.param(
        "HEVC 4K AC3 MVO UKR",
        [expect_track("uk", "MVO")],
        {"quality": "4K", "codec": "HEVC"},
        id="hevc-4k-mvo-ukr",
    ),
    pytest.param(
        "Дублированный [Русский | 4K, SDR]",
        [expect_track("ru", "DUB")],
        {"quality": "4K"},
        id="dub-russian-4k",
    ),
    pytest.param(
        "Оригинал [Eng]",
        [expect_track("en", "OG")],
        {},
        id="original-eng",
    ),
    pytest.param(
        "Original",
        [expect_track("en", "OG")],
        {},
        id="original-bare",
    ),
    pytest.param(
        "Одноголосый, P - А.Михалев",
        [expect_track("ru", "AVO", "А.Михалев")],
        {},
        id="avo-mikhalev",
    ),
    pytest.param(
        "MVO FGiashdfu",
        [expect_track("ru", "MVO", "FGiashdfu")],
        {},
        id="mvo-unknown-org",
    ),
    pytest.param(
        "MVO",
        [expect_track("ru", "MVO")],
        {},
        id="bare-mvo",
    ),
    pytest.param(
        "Режиссерская версия DUB RUS",
        [expect_track("ru", "DUB")],
        {"edition": "directors_cut"},
        id="directors-cut-dub-rus",
    ),
    pytest.param(
        "Extended Edition MVO LostFilm",
        [expect_track("ru", "MVO", "LostFilm")],
        {"edition": "extended"},
        id="extended-lostfilm",
    ),
    pytest.param(
        "Director's Cut 4K HDR10",
        [expect_track("ru", None)],
        {"hdr": "HDR10", "quality": "4K", "edition": "directors_cut"},
        id="directors-cut-4k-hdr10",
    ),
    pytest.param(
        "IMAX DUB HEVC",
        [expect_track("ru", "DUB")],
        {"codec": "HEVC", "edition": "imax"},
        id="imax-dub-hevc",
    ),
    pytest.param(
        "Дубльований UATeam",
        [expect_track("uk", "DUB", "UATeam")],
        {},
        id="uk-dub-uateam",
    ),
    pytest.param(
        "1+1 [Український | 4K, SDR]",
        [expect_track("uk", None, "1+1")],
        {"quality": "4K"},
        id="ukrainian-11-4k",
    ),
]


@pytest.mark.parametrize("label,expected_tracks,expected_tech", VOICEOVER_CASES)
def test_parse_voiceover(label, expected_tracks, expected_tech):
    result = FilmixPrivate._parse_voiceover(label, original_lang="en")

    assert len(result.tracks) == len(expected_tracks), (
        f"Expected {len(expected_tracks)} tracks, got {len(result.tracks)}: {result.tracks}"
    )
    for track, expected in zip(result.tracks, expected_tracks):
        assert _key(track.lang) == expected.lang
        assert _key(track.voice_type) == expected.voice_type
        assert _org_ids(track) == expected.orgs

    for attr in ("quality", "codec", "hdr", "edition"):
        expected = expected_tech.get(attr)
        assert _key(getattr(result, attr)) == expected, (
            f"{attr}: expected {expected}, got {_key(getattr(result, attr))}"
        )


def test_parse_track_keeps_multiple_orgs_in_single_track_mode():
    track = Filmix.build_parser().parse_track("LostFilm MVO MVO Amedia")

    assert track.voice_type and track.voice_type.id == "MVO"
    assert _org_ids(track) == ("LostFilm", "Amedia")


def test_parse_voiceover_uses_supported_asian_original_language():
    result = FilmixPrivate._parse_voiceover("Original", original_lang="zh")

    assert len(result.tracks) == 1
    assert _key(result.tracks[0].lang) == "zh"
    assert _key(result.tracks[0].voice_type) == "OG"
