import json

import numpy as np
import pytest

from pipeline import naming_brief as nb

KEYS = ["c001", "c002", "c003"]


def registry():
    return {
        "next_key": 5,
        "clusters": {
            "c001": {
                "name": "Minecraft & SMPs",
                "source": "seed",
                "active": True,
                "size": 2,
                "keywords": ["minecraft"],
                "colour": "#111111",
            },
            "c002": {
                "name": "tech · technology",
                "source": "placeholder",
                "active": True,
                "size": 2,
                "keywords": ["tech", "technology"],
                "colour": "#222222",
            },
            "c003": {
                "name": "cook · food",
                "source": "placeholder",
                "active": True,
                "size": 2,
                "keywords": ["cook", "food"],
                "colour": "#333333",
            },
            "c004": {
                "name": "Old Gone",
                "source": "seed",
                "active": False,
                "size": 0,
                "keywords": [],
                "colour": "#444444",
            },
        },
    }


def fixture():
    ids = ["a", "b", "c", "d", "e", "f"]
    records = {
        "a": {
            "id": "a",
            "title": "Blockman",
            "description": "Blockman is a Minecraft YouTuber. More.",
        },
        "b": {"id": "b", "title": "Crafty", "description": "Crafty is a Minecraft builder."},
        "c": {
            "id": "c",
            "title": "Gadget Gus",
            "description": "Gus Smith (born May 1, 1990), better known as Gadget Gus, is a tech reviewer who reviews phones.",
        },
        "d": {"id": "d", "title": "Chip", "description": "Chip is a technology channel."},
        "e": {"id": "e", "title": "Chef Bo", "description": "Chef Bo is a cooking YouTuber."},
        "f": {"id": "f", "title": "Pan", "description": "Pan is a food vlogger."},
    }
    labels = np.array([0, 0, 1, 1, 2, 2])
    X = np.array(
        [[1, 0, 0], [0.9, 0.1, 0], [0, 1, 0], [0.1, 0.9, 0], [0, 0, 1], [0, 0.2, 0.9]],
        dtype=np.float32,
    )
    X /= np.linalg.norm(X, axis=1, keepdims=True)
    centroids = np.eye(3, dtype=np.float32)
    return ids, records, labels, X, centroids


def brief(owner=None, **kw):
    ids, records, labels, X, centroids = fixture()
    return nb.build_brief(
        KEYS, registry(), owner or {}, labels, X, centroids, ids, records, frozenset(), **kw
    )


# ---- which clusters need names -------------------------------------------------------------


def test_unnamed_keys_are_placeholders_without_an_owner_name():
    assert nb.unnamed_keys(KEYS, registry(), {}) == ["c002", "c003"]
    assert nb.unnamed_keys(KEYS, registry(), {"c003": "Cooking"}) == ["c002"]


def test_current_names_prefer_owner_names_and_skip_placeholders():
    assert nb.current_names(KEYS, registry(), {"c001": "Minecraft Builds"}) == {
        "c001": "Minecraft Builds"
    }


# ---- the brief -----------------------------------------------------------------------------


def test_brief_has_a_section_per_unnamed_cluster_only():
    text = brief()
    assert "### c002" in text and "### c003" in text
    assert "### c001" not in text


def test_brief_lists_taken_names_including_owner_overrides():
    text = brief(owner={"c001": "Minecraft Builds"})
    assert "Minecraft Builds" in text
    assert "Minecraft & SMPs" not in text  # overridden name is not shown as taken


def test_brief_skips_clusters_the_owner_already_named():
    text = brief(owner={"c003": "Cooking"})
    assert "### c003" not in text
    assert "Cooking" in text  # now a taken name


def test_brief_asks_for_json_with_exactly_the_unnamed_keys():
    text = brief()
    assert '"c002": "' in text and '"c003": "' in text
    assert '"c001": "' not in text
    assert "JSON" in text


def test_brief_snippets_use_cleaned_text_without_the_name_lead():
    text = brief()
    assert "is a tech reviewer who reviews phones" in text
    assert "born May 1" not in text


def test_brief_orders_creators_nearest_the_centre_first():
    text = brief()
    section = text.split("### c003")[1]
    assert section.index("Chef Bo") < section.index("Pan")


def test_brief_names_the_nearest_other_clusters():
    ids, records, labels, X, centroids = fixture()
    centroids = np.array([[1, 0, 0], [0.8, 0.6, 0], [0, 0, 1]], dtype=np.float32)
    text = nb.build_brief(
        KEYS, registry(), {}, labels, X, centroids, ids, records, frozenset(), neighbours=1
    )
    section = text.split("### c002")[1].split("###")[0]
    assert "c001" in section and "Minecraft & SMPs" in section


def test_brief_with_nothing_to_name_says_so():
    text = brief(owner={"c002": "Tech", "c003": "Cooking"})
    assert "Nothing to name" in text


# ---- reading the chat reply ----------------------------------------------------------------


def test_parse_reply_reads_plain_json():
    assert nb.parse_reply('{"c002": "Tech Reviews"}') == {"c002": "Tech Reviews"}


def test_parse_reply_finds_json_inside_prose_and_code_fences():
    reply = 'Here you go!\n\n```json\n{\n  "c002": "Tech Reviews",\n  "c003": "Cooking & Food"\n}\n```\nEnjoy.'
    assert nb.parse_reply(reply) == {"c002": "Tech Reviews", "c003": "Cooking & Food"}


def test_parse_reply_tolerates_a_trailing_comma():
    assert nb.parse_reply('{"c002": "Tech",\n}') == {"c002": "Tech"}


def test_parse_reply_without_json_raises():
    with pytest.raises(ValueError, match="JSON"):
        nb.parse_reply("Sorry, I can't help with that.")


def test_parse_reply_rejects_non_object_json():
    with pytest.raises(ValueError):
        nb.parse_reply('["Tech"]')


# ---- merging into cluster_names.json -------------------------------------------------------


def test_merge_adds_new_names_and_strips_whitespace():
    merged, rep = nb.merge_names({}, {"c002": "  Tech Reviews "}, KEYS, registry())
    assert merged == {"c002": "Tech Reviews"}
    assert rep["added"] == ["c002"]


def test_merge_keeps_existing_names_unless_forced():
    merged, rep = nb.merge_names({"c002": "Mine"}, {"c002": "Theirs"}, KEYS, registry())
    assert merged == {"c002": "Mine"} and rep["kept"] == ["c002"]
    merged, rep = nb.merge_names({"c002": "Mine"}, {"c002": "Theirs"}, KEYS, registry(), force=True)
    assert merged == {"c002": "Theirs"} and rep["replaced"] == ["c002"]


def test_merge_same_name_again_is_not_a_change():
    merged, rep = nb.merge_names({"c002": "Tech"}, {"c002": "Tech"}, KEYS, registry())
    assert merged == {"c002": "Tech"} and rep["kept"] == [] and rep["added"] == []


def test_merge_rejects_unknown_retired_and_empty_entries():
    reply = {"c999": "Ghost", "c004": "Old Gone", "c003": "   ", "c002": 7}
    merged, rep = nb.merge_names({}, reply, KEYS, registry())
    assert merged == {}
    assert rep["unknown"] == ["c004", "c999"]
    assert rep["invalid"] == ["c002", "c003"]


def test_merge_reports_names_used_by_two_active_clusters():
    _, rep = nb.merge_names({}, {"c002": "Minecraft & SMPs", "c003": "Food"}, KEYS, registry())
    assert rep["duplicates"] == {"Minecraft & SMPs": ["c001", "c002"]}


def test_merge_duplicate_check_is_case_insensitive():
    _, rep = nb.merge_names({}, {"c002": "Food", "c003": "food"}, KEYS, registry())
    assert rep["duplicates"] == {"Food": ["c002", "c003"]}


def test_import_reply_writes_the_names_file(tmp_path):
    names_file = tmp_path / "cluster_names.json"
    names_file.write_text(json.dumps({"c001": "Builds"}), encoding="utf-8")
    rep = nb.import_reply('```json\n{"c002": "Tech"}\n```', names_file, KEYS, registry())
    assert json.loads(names_file.read_text(encoding="utf-8")) == {"c001": "Builds", "c002": "Tech"}
    assert rep["added"] == ["c002"]


def test_import_reply_dry_run_writes_nothing(tmp_path):
    names_file = tmp_path / "cluster_names.json"
    nb.import_reply('{"c002": "Tech"}', names_file, KEYS, registry(), dry_run=True)
    assert not names_file.exists()


def test_import_reply_refuses_a_broken_names_file(tmp_path):
    names_file = tmp_path / "cluster_names.json"
    names_file.write_text('{"c001": "Builds",,}', encoding="utf-8")
    with pytest.raises(ValueError, match="cluster_names.json"):
        nb.import_reply('{"c002": "Tech"}', names_file, KEYS, registry())
    assert names_file.read_text(encoding="utf-8") == '{"c001": "Builds",,}'


def test_format_report_mentions_each_problem():
    rep = {
        "added": ["c002"],
        "replaced": [],
        "kept": ["c003"],
        "unknown": ["c999"],
        "invalid": [],
        "duplicates": {"Food": ["c002", "c003"]},
    }
    out = nb.format_report(rep)
    assert "c002" in out and "c999" in out and "Food" in out and "FORCE=1" in out


def test_snippet_reads_past_a_short_first_sentence_and_cuts_on_a_word():
    rec = {
        "id": "x",
        "title": "Zed",
        "description": "Zed is a YouTuber. He plays horror games " + "and more " * 40,
    }
    out = nb._snippet(rec, frozenset())
    assert out.startswith("is a YouTuber. He plays horror games")
    assert out.endswith("…") and len(out) <= nb.SNIPPET_CHARS
    assert out[:-1].endswith(("and", "more"))
