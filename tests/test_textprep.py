from pipeline.textprep import (
    chunk_text,
    clean_text,
    embed_chunks,
    keyword_text,
    protected_words,
    text_hash,
)

PROTECTED = frozenset({"American", "Minecraft", "YouTuber"})


# --- clean_text --------------------------------------------------------------------------------


def test_lead_and_names_removed():
    rec = {
        "title": "Vsauce",
        "description": "Not to be confused with Vinesauce. Michael David Stevens "
        "(born: January 23, 1986), better known online as Vsauce, is an American educational YouTuber. "
        "Vsauce creates educational content. Michael hosts Mind Field.",
    }
    out = clean_text(rec, PROTECTED)
    assert out.startswith("is an American educational YouTuber.")
    for name in ("Vsauce", "Michael", "Stevens", "Vinesauce", "January"):
        assert name not in out
    assert "creates educational content" in out and "Mind Field" in out


def test_protected_topic_words_survive():
    rec = {"title": "Minecraft Universe", "description": "Minecraft Universe is a channel about Minecraft maps."}
    assert clean_text(rec, PROTECTED) == "is a channel about Minecraft maps."


def test_no_lead_verb_keeps_text_but_drops_title():
    rec = {"title": "Bob", "description": "Bob uploads cooking videos weekly"}
    assert clean_text(rec, PROTECTED) == "uploads cooking videos weekly"


def test_names_removed_case_insensitively_and_possessives():
    rec = {"title": "PewDiePie", "description": "Felix Kjellberg, known as PewDiePie, is a Swedish YouTuber. "
           "Felix's fans call him pewdiepie."}
    out = clean_text(rec, PROTECTED)
    assert "Felix" not in out and "pewdiepie" not in out.lower() and "Kjellberg" not in out
    assert "Swedish YouTuber" in out


def test_empty_after_cleaning_falls_back_to_title():
    assert clean_text({"title": "Zed", "description": None}, PROTECTED) == "Zed"
    assert clean_text({"title": "Zed", "description": "Zed"}, PROTECTED) == "Zed"


def test_lead_verb_only_searched_near_the_start():
    rec = {"title": "Q", "description": "Cooking Tips " + "and more " * 60 + "This is fine."}
    out = clean_text(rec, PROTECTED)
    assert out.startswith("Cooking Tips")  # verb is past 400 chars: no lead stripped


def test_protected_words_threshold():
    recs = [{"description": "Minecraft fun"}] * 3 + [{"description": "Alex plays"}] + [{"description": None}] * 6
    assert protected_words(recs, min_df=0.2) == frozenset({"Minecraft", "fun"})


# --- chunking ----------------------------------------------------------------------------------


def test_chunking_word_boundaries_and_cap():
    assert chunk_text("aa bb cc dd ee", max_chars=5, max_chunks=2) == (["aa bb", "cc dd"], True)
    assert chunk_text("aa bb", 5, 8) == (["aa bb"], False)


def test_chunk_backs_off_to_word_boundary():
    assert chunk_text("alpha beta gamma delta", max_chars=12, max_chunks=8) == (["alpha beta", "gamma delta"], False)


def test_chunk_hard_cut_when_no_space():
    chunks, cut = chunk_text("x" * 12, max_chars=5, max_chunks=8)
    assert chunks == ["xxxxx", "xxxxx", "xx"] and not cut


def test_embed_chunks_and_keyword_text():
    rec = {"title": "Bob", "description": "Bob is a chef. " + "cooks food " * 400}
    chunks, cut = embed_chunks(rec, PROTECTED, max_chars=2000, max_chunks=8)
    assert len(chunks) == 3 and not cut and chunks[0].startswith("is a chef.")
    assert keyword_text(rec, PROTECTED, max_chars=2000) == chunks[0]


def test_text_hash_depends_on_every_chunk_and_model():
    assert text_hash(["a", "b"], "m") != text_hash(["a", "c"], "m")
    assert text_hash(["a", "b"], "m") != text_hash(["a", "b"], "n")
    assert text_hash(["ab"], "m") != text_hash(["a", "b"], "m")
    assert text_hash(["a"], "m") == text_hash(["a"], "m")
