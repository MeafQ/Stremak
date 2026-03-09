from streaming.parsing.catalog import default_profile

parser = default_profile.build_parser()


def test_parse_fuzzy_residual_studio_is_canonicalized():
    track = parser.parse_track("MVO Red Hed Sound")

    assert track.voice_type and track.voice_type.id == "MVO"
    assert [org.id for org in track.orgs] == ["Red Head Sound"]


def test_parse_unknown_residual_text_can_infer_lang_from_script():
    label = "MVO Їжак"
    track = parser.parse_track(label)

    assert track.voice_type and track.voice_type.id == "MVO"
    assert len(track.orgs) == 1
    assert track.orgs[0].kind == "unknown"
    assert track.orgs[0].id == "Їжак"
    assert track.lang and track.lang.id == "uk"
