import json

import pytest


def test_status_reports_demo_mode(service):
    status = json.loads(service.get_pipeline_status())
    assert status["status"].startswith("online")
    assert "demo" in status["status"]
    assert status["queue_stats"]["pending_topics_count"] == 3
    assert status["queue_stats"]["completed_drafts_count"] == 1


def test_list_pending_topics_reads_front_matter(service):
    topics = json.loads(service.list_pending_topics())
    titles = {t["title"] for t in topics}
    assert "Villas with private pools in Vagator" in titles
    villa = next(t for t in topics if "Vagator" in t["title"])
    assert villa["sources_count"] == 4


def test_list_pending_topics_caps_at_twelve(service):
    assert len(json.loads(service.list_pending_topics())) <= 12


def test_topic_sources_parse_platform_title_url(service):
    sources = json.loads(service.get_topic_sources("Vagator"))
    assert sources and {"platform", "title", "url"} <= sources[0].keys()


def test_suggest_picks_a_business_relevant_topic(service):
    suggestion = json.loads(service.suggest_next_article())
    assert "Vagator" in suggestion["topic"]
    assert suggestion["sources_count"] == 4


def test_write_article_demo_creates_labelled_draft(service):
    result = json.loads(service.write_article("Quiet beaches in Benaulim"))
    assert result["status"] == "completed (demo)"
    draft = json.loads(service.get_draft(result["filename"]))
    assert "Demo-mode placeholder" in draft["content"]


def test_write_article_rejects_empty_topic(service):
    with pytest.raises(ValueError):
        service.write_article("   ")


def test_style_check_flags_cliches(service):
    service.save_draft("cliche.md", "# Title\n\nGoa is a hidden gem. Moreover, it is vibrant.\n\n## Section\nText.")
    audit = json.loads(service.run_style_check("cliche.md"))
    assert {"hidden gem", "moreover", "vibrant"} <= set(audit["ai_cliches_found"])
    assert audit["brand_score"] < 100


def test_style_check_clean_draft_scores_100(service):
    audit = json.loads(service.run_style_check("sample-assagao"))
    assert audit["brand_score"] == 100
    assert "Includes Pexels attribution" in audit["passed_checks"]


def test_missing_draft_raises(service):
    with pytest.raises(ValueError):
        service.get_draft("does-not-exist")


def test_save_draft_rejects_path_like_names(service, tmp_path):
    with pytest.raises(ValueError):
        service.save_draft("../../escape.md", "x")
    assert not (tmp_path / "escape.md").exists()


def test_push_requires_real_pipeline(service):
    with pytest.raises(RuntimeError):
        service.push_to_github("anything.md")


def test_scanner_skipped_in_demo_mode(service):
    result = json.loads(service.run_scanner())
    assert result["status"].startswith("skipped")


def test_suggest_skips_topics_that_already_have_a_draft(service):
    first = json.loads(service.suggest_next_article())["topic"]
    service.write_article(first)
    second = json.loads(service.suggest_next_article())["topic"]
    assert second != first


def test_suggest_raises_when_every_topic_is_drafted(service):
    for t in json.loads(service.list_pending_topics()):
        service.write_article(t["title"])
    with pytest.raises(ValueError):
        service.suggest_next_article()


def test_snippet_is_readable_not_raw_front_matter(service):
    for topic in json.loads(service.list_pending_topics()):
        assert not topic["snippet"].startswith("---")
        assert "date:" not in topic["snippet"]


def test_source_with_empty_url_is_still_listed(service, tmp_path):
    review = next(p for p in __import__("pathlib").Path(__import__("os").environ["WAYZYY_REVIEW_DIR"]).glob("*.md"))
    review.write_text(
        "---\nkeyword: Empty url topic\nplatforms: research\nclassification: new_pillar\n---\n\n"
        "## Trend Sources\n- [research] [Mentioned while researching X]()\n",
        encoding="utf-8",
    )
    sources = json.loads(service.get_topic_sources("Empty url topic"))
    assert sources == [{"platform": "research", "title": "Mentioned while researching X", "url": ""}]


def test_find_similar_articles_falls_back_to_keywords(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    results = json.loads(service.find_similar_articles("cafe guide in Assagao"))
    assert results[0]["filename"].endswith("assagao-cafe-guide.md")
    assert results[0]["engine"] == "keyword-overlap"


def test_find_similar_articles_survives_unreachable_sie(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://127.0.0.1:9")
    results = json.loads(service.find_similar_articles("assagao cafe"))
    assert results and results[0]["engine"] == "keyword-overlap"


def test_find_similar_articles_rejects_empty_query(service):
    with pytest.raises(ValueError):
        service.find_similar_articles("  ")


def test_find_similar_articles_defaults_a_missing_limit(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    assert json.loads(service.find_similar_articles("assagao cafe", None))


def test_compare_search_engines_without_sie(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    out = json.loads(service.compare_search_engines("assagao cafe", 2))
    assert out["keyword"]["results"][0]["filename"].endswith("assagao-cafe-guide.md")
    assert len(out["keyword"]["results"]) <= 2
    assert out["sie"]["available"] is False and "SIE_URL" in out["sie"]["message"]


def test_compare_search_engines_reports_unreachable_sie(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://127.0.0.1:9")
    out = json.loads(service.compare_search_engines("assagao cafe", None))
    assert out["sie"]["available"] is False and "not reachable" in out["sie"]["message"]
    assert out["keyword"]["results"]


def test_compare_search_engines_uses_sie_when_up(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://sie")
    monkeypatch.setattr(
        "article_receiver.service._embed_with_sie",
        lambda texts: [[1.0, 0.0]] + [[float(i == 0), float(i != 0)] for i in range(len(texts) - 1)],
    )
    out = json.loads(service.compare_search_engines("anything", 1))
    assert out["sie"]["available"] is True
    assert out["sie"]["results"][0]["engine"].startswith("sie:")


def test_sie_embeds_each_draft_once(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://sie")
    monkeypatch.setattr("article_receiver.service._EMBED_CACHE", {})
    calls = []

    def fake(texts):
        calls.append(len(texts))
        return [[1.0, float(i)] for i in range(len(texts))]

    monkeypatch.setattr("article_receiver.service._embed_with_sie", fake)
    service.find_similar_articles("first", 2)
    service.find_similar_articles("second", 2)
    assert calls[0] > 1 and calls[1] == 1  # second search embeds only the query


# ── Phase 1: brand relevance and coverage with SIE (embeddings faked by keyword) ──

def _fake_sie(monkeypatch):
    """Fake SIE: a text's vector is [on-brand, politics, cafe, villa]."""
    def embed(texts):
        out = []
        for t in texts:
            t = t.lower()
            out.append([
                float(any(w in t for w in ("goa", "villa", "beach", "cafe", "travel", "monsoon"))),
                float("bjp" in t),
                float("cafe" in t),
                float("villa" in t),
            ])
        return out

    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://sie")
    monkeypatch.setattr("article_receiver.service._EMBED_CACHE", {})
    monkeypatch.setattr("article_receiver.service._embed_with_sie", embed)


def _add_offbrand_topic(sources=50):
    import os, pathlib
    review = pathlib.Path(os.environ["WAYZYY_REVIEW_DIR"])
    links = "\n".join(f"- [news] [Story {i}](https://example.com/{i})" for i in range(sources))
    (review / "2026-01-09_bjp-dispute.md").write_text(
        f"---\nkeyword: BJP dispute\n---\n\n## Trend Sources\n{links}\n", encoding="utf-8")


def test_keyword_suggest_picks_a_popular_offbrand_topic(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    _add_offbrand_topic()
    suggestion = json.loads(service.suggest_next_article())
    assert suggestion["topic"] == "BJP dispute"  # the behaviour SIE fixes
    assert suggestion["engine"] == "keyword" and suggestion["relevance"] is None


def test_sie_suggest_skips_offbrand_and_covered_topics(service, monkeypatch):
    _fake_sie(monkeypatch)
    _add_offbrand_topic()
    suggestion = json.loads(service.suggest_next_article())
    assert "Vagator" in suggestion["topic"]
    assert suggestion["skipped_off_brand"] == 1  # BJP dispute
    assert suggestion["skipped_covered"] == 1  # cafes topic vs the Assagao cafe draft
    assert suggestion["engine"].startswith("keyword + sie:")
    assert suggestion["relevance"] > 0.25 and "Superlinked SIE" in suggestion["rationale"]


def test_sie_suggest_explains_when_nothing_is_left(service, monkeypatch):
    _fake_sie(monkeypatch)
    monkeypatch.setitem(__import__("article_receiver.service", fromlist=["CONFIG"]).CONFIG["semantic"], "min_relevance", 2.0)
    with pytest.raises(ValueError, match="min_relevance"):
        service.suggest_next_article()


def test_unreachable_sie_keeps_keyword_suggestions(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    expected = json.loads(service.suggest_next_article())["topic"]
    monkeypatch.setattr("article_receiver.service.SIE_URL", "http://127.0.0.1:9")
    suggestion = json.loads(service.suggest_next_article())
    assert suggestion["topic"] == expected and suggestion["engine"] == "keyword"


def test_topic_list_shows_relevance_and_coverage(service, monkeypatch):
    _fake_sie(monkeypatch)
    topics = {t["title"].lower(): t for t in json.loads(service.list_pending_topics())}
    cafes = next(t for k, t in topics.items() if "cafe" in k)
    villas = next(t for k, t in topics.items() if "villa" in k)
    assert cafes["covered_by"].endswith("assagao-cafe-guide.md")
    assert villas["covered_by"] == "" and villas["relevance"] > 0.25


def test_topic_list_without_sie_has_no_relevance(service, monkeypatch):
    monkeypatch.setattr("article_receiver.service.SIE_URL", "")
    assert all(t["relevance"] is None for t in json.loads(service.list_pending_topics()))
