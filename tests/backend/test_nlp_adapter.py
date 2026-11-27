"""Unit tests for constrained NLP adapters, caching, vocabulary check, and fallback."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.backend.conftest import SAMPLE_CUISINE_MAP_CSV
from web.backend.constants import QUERY_LOG_MAX_CHARS
from web.backend.repositories.meta_repository import VocabularySnapshot
from web.backend.schemas.nlp import NLSearchRequest, SearchParams
from web.backend.services.nlp_adapter import (
    HuggingFaceAdapter,
    NLPProviderError,
    RuleBasedParser,
    load_cuisine_synonyms,
    validate_against_vocabulary,
)
from web.backend.services.rate_limiter import SlidingWindowRateLimiter
from web.backend.services.search_service import SearchService
from web.backend.settings import BackendSettings


def test_search_params_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SearchParams(city="London", raw_sql="SELECT * FROM restaurants")  # type: ignore[call-arg]


def test_rule_based_parser_extracts_filters_and_synonyms(
    sample_vocabulary: VocabularySnapshot,
    tmp_path: Path,
) -> None:
    map_path = tmp_path / "cuisine_map.csv"
    map_path.write_text(SAMPLE_CUISINE_MAP_CSV, encoding="utf-8")
    synonyms = load_cuisine_synonyms(map_path)

    parser = RuleBasedParser(sample_vocabulary, cuisine_synonyms=synonyms)
    parsed = parser.parse(
        "Affordable Italian in New Delhi with rating above 4.2 "
        "under 1500 and online delivery"
    )

    assert parsed.city == "New Delhi"
    assert parsed.cuisine == ["Italian"]
    assert parsed.min_rating == 4.2
    assert parsed.max_cost_for_two == 1500.0
    assert parsed.price_range == 2
    assert parsed.has_online_delivery is True
    assert parsed.needs_clarification is None


def test_rule_based_parser_handles_aliases_usd_and_clarification(
    sample_vocabulary: VocabularySnapshot,
) -> None:
    parser = RuleBasedParser(sample_vocabulary, cuisine_synonyms={"malay": "Malaysian"})

    uk_parsed = parser.parse("Malay food in UK under $40 with table booking")
    assert uk_parsed.country == "United Kingdom"
    assert uk_parsed.cuisine == ["Malaysian"]
    assert uk_parsed.max_cost_usd == 40.0
    assert uk_parsed.has_table_booking is True

    unclear = parser.parse("hello world xyz123")
    assert unclear.needs_clarification is not None


def test_rule_based_parser_prevents_cuisine_overlap_and_flags_unknown_location(
    sample_vocabulary: VocabularySnapshot,
) -> None:
    extended_vocab = VocabularySnapshot(
        countries=sample_vocabulary.countries,
        cities=sample_vocabulary.cities,
        localities=sample_vocabulary.localities,
        cuisines=tuple(
            dict.fromkeys([*sample_vocabulary.cuisines, "North Indian", "Indian"])
        ),
        cuisine_groups=sample_vocabulary.cuisine_groups,
        cuisine_synonyms=sample_vocabulary.cuisine_synonyms,
    )
    parser = RuleBasedParser(extended_vocab)

    north_indian = parser.parse(
        "Affordable North Indian in New Delhi with online delivery"
    )
    assert north_indian.city == "New Delhi"
    assert north_indian.cuisine == ["North Indian"]
    assert north_indian.needs_clarification is None

    unknown_city = parser.parse("best sushi in Cairo")
    assert unknown_city.city is None
    assert unknown_city.needs_clarification is not None
    assert "Cairo" in unknown_city.needs_clarification

    unknown_manila = parser.parse("cheap chinese in Manila")
    assert unknown_manila.city is None
    assert unknown_manila.needs_clarification is not None
    assert "Manila" in unknown_manila.needs_clarification


def test_huggingface_adapter_validates_vocabulary_strips_think_and_caches(
    sample_vocabulary: VocabularySnapshot,
    test_settings: BackendSettings,
) -> None:
    calls: list[str] = []
    now = [100.0]

    def fake_completion(
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        calls.append(messages[-1]["content"])
        assert temperature == 0.0
        assert max_tokens <= 256
        return "<think>reasoning</think>\n" + json.dumps(
            {
                "country": "india",
                "city": "new delhi",
                "locality": "connaught place",
                "cuisine": ["italian", "MartianFood"],
                "cuisine_group": None,
                "min_rating": 4.2,
                "min_cost_for_two": None,
                "max_cost_for_two": 1500,
                "max_cost_usd": None,
                "price_range": None,
                "has_online_delivery": True,
                "has_table_booking": None,
                "search_query": None,
                "needs_clarification": None,
            }
        )

    configured_settings = test_settings.model_copy(
        update={
            "nlp_cache_ttl_seconds": 60,
            "nlp_cache_max_entries": 2,
        }
    )
    adapter = HuggingFaceAdapter(
        vocabulary=sample_vocabulary,
        app_settings=configured_settings,
        completion_fn=fake_completion,
        clock=lambda: now[0],
    )

    first = adapter.parse("Italian in New Delhi above 4.2")
    assert first.country == "India"
    assert first.city == "New Delhi"
    assert first.locality == "Connaught Place"
    assert first.cuisine == ["Italian"]
    assert len(calls) == 1

    # Cache hit
    second = adapter.parse("  italian in new delhi above 4.2  ")
    assert second == first
    assert len(calls) == 1

    # Cache expires after TTL
    now[0] = 200.0
    adapter.parse("Italian in New Delhi above 4.2")
    assert len(calls) == 2


def test_huggingface_adapter_rejects_bad_outputs(
    sample_vocabulary: VocabularySnapshot,
    test_settings: BackendSettings,
) -> None:
    def raise_timeout(**_kwargs: object) -> str:
        raise TimeoutError("timed out")

    timeout_adapter = HuggingFaceAdapter(
        vocabulary=sample_vocabulary,
        app_settings=test_settings,
        completion_fn=raise_timeout,
    )
    with pytest.raises(NLPProviderError):
        timeout_adapter.parse("Italian in New Delhi")

    def extra_key_output(**_kwargs: object) -> str:
        return json.dumps({"city": "London", "unexpected_sql": "DROP TABLE"})

    extra_adapter = HuggingFaceAdapter(
        vocabulary=sample_vocabulary,
        app_settings=test_settings,
        completion_fn=extra_key_output,
    )
    with pytest.raises(NLPProviderError):
        extra_adapter.parse("Food in London")

    def bad_json_output(**_kwargs: object) -> str:
        return "not json at all"

    bad_adapter = HuggingFaceAdapter(
        vocabulary=sample_vocabulary,
        app_settings=test_settings,
        completion_fn=bad_json_output,
    )
    with pytest.raises(NLPProviderError):
        bad_adapter.parse("Food in London")


def test_validate_against_vocabulary_drops_unknowns(
    sample_vocabulary: VocabularySnapshot,
) -> None:
    raw = SearchParams(
        country="Atlantis",
        city="london",
        cuisine=["British", "UnknownCuisine"],
    )
    cleaned = validate_against_vocabulary(raw, sample_vocabulary)
    assert cleaned.country is None
    assert cleaned.city == "London"
    assert cleaned.cuisine == ["British"]


def test_search_service_falls_back_and_truncates_logged_query(
    sample_vocabulary: VocabularySnapshot,
    test_settings: BackendSettings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from web.backend.repositories.meta_repository import MetaRepository
    from web.backend.repositories.restaurant_repository import RestaurantRepository

    def failing_completion(**_kwargs: object) -> str:
        raise TimeoutError("HF timed out")

    hf_adapter = HuggingFaceAdapter(
        vocabulary=sample_vocabulary,
        app_settings=test_settings,
        completion_fn=failing_completion,
    )
    rule_adapter = RuleBasedParser(vocabulary=sample_vocabulary)
    service = SearchService(
        restaurant_repository=RestaurantRepository(None, test_settings),
        meta_repository=MetaRepository(None, test_settings),
        rate_limiter=SlidingWindowRateLimiter(max_requests=30),
        app_settings=test_settings,
        primary_adapter=hf_adapter,
        fallback_adapter=rule_adapter,
    )

    long_query = "Italian in New Delhi above 4.2 " + ("x" * 350)
    assert len(long_query) <= 500

    with caplog.at_level(logging.INFO, logger="web.backend.services.search_service"):
        response = service.search_natural_language(
            NLSearchRequest(query=long_query, limit=10, offset=0),
            client_key="127.0.0.1",
        )

    assert response.parser_used == "rule_based"
    assert response.fallback_used is True
    assert response.total == 1
    assert response.items[0].name == "Pasta Palace"

    info_records = [rec for rec in caplog.records if hasattr(rec, "query_preview")]
    assert info_records
    logged_preview = info_records[-1].query_preview
    assert len(logged_preview) == QUERY_LOG_MAX_CHARS
    assert logged_preview == long_query[:QUERY_LOG_MAX_CHARS]


class _FakeSemanticMatcher:
    """Offline semantic matcher stub for unit tests."""

    def is_ready(self) -> bool:
        return True

    def is_off_topic(self, query: str) -> bool:
        return "weather" in query.lower() or "laptops" in query.lower()

    def match_cuisines(self, query: str, top_k: int = 2) -> list[str]:
        q_lower = query.lower()
        if "tacos" in q_lower:
            return ["Mexican"][:top_k]
        if "spicy curry" in q_lower:
            return ["North Indian"][:top_k]
        if "dinner" in q_lower:
            return ["Diner"][:top_k]
        return []

    def match_price_range(self, query: str) -> int | None:
        if "romantic fancy" in query.lower():
            return 4
        return None


def test_semantic_hybrid_parser_aliases_typos_and_service_label(
    sample_vocabulary: VocabularySnapshot,
    test_settings: BackendSettings,
) -> None:
    from web.backend.repositories.meta_repository import MetaRepository
    from web.backend.repositories.restaurant_repository import RestaurantRepository

    extended_vocab = VocabularySnapshot(
        countries=sample_vocabulary.countries,
        cities=tuple(
            dict.fromkeys([*sample_vocabulary.cities, "Mumbai", "Singapore", "Dubai"])
        ),
        localities=sample_vocabulary.localities,
        cuisines=tuple(
            dict.fromkeys([*sample_vocabulary.cuisines, "Mexican", "North Indian"])
        ),
        cuisine_groups=sample_vocabulary.cuisine_groups,
        cuisine_synonyms=sample_vocabulary.cuisine_synonyms,
    )
    hybrid = RuleBasedParser(
        extended_vocab,
        semantic_matcher=_FakeSemanticMatcher(),
    )

    bombay = hybrid.parse("Italian in Bombay")
    assert bombay.city == "Mumbai"
    assert bombay.cuisine == ["Italian"]

    typo_london = hybrid.parse("tacos in Londn")
    assert typo_london.city == "London"
    assert typo_london.cuisine == ["Mexican"]

    vibe = hybrid.parse("romantic fancy dinner in Dubai")
    assert vibe.city == "Dubai"
    assert vibe.price_range == 4

    still_unknown = hybrid.parse("best sushi in Cairo")
    assert still_unknown.needs_clarification is not None

    def failing_completion(**_kwargs: object) -> str:
        raise TimeoutError("HF timed out")

    hf_adapter = HuggingFaceAdapter(
        vocabulary=extended_vocab,
        app_settings=test_settings,
        completion_fn=failing_completion,
    )
    service = SearchService(
        restaurant_repository=RestaurantRepository(None, test_settings),
        meta_repository=MetaRepository(None, test_settings),
        rate_limiter=SlidingWindowRateLimiter(max_requests=30),
        app_settings=test_settings,
        primary_adapter=hf_adapter,
        fallback_adapter=hybrid,
    )
    response = service.search_natural_language(
        NLSearchRequest(query="Italian in Bombay", limit=10, offset=0),
        client_key="127.0.0.1",
    )
    assert response.parser_used == "huggingface_semantic"
    assert response.fallback_used is True


def test_off_topic_guardrails_and_filler_stripping(
    sample_vocabulary: VocabularySnapshot,
) -> None:
    extended_vocab = VocabularySnapshot(
        countries=sample_vocabulary.countries,
        cities=tuple(dict.fromkeys([*sample_vocabulary.cities, "Dubai"])),
        localities=sample_vocabulary.localities,
        cuisines=tuple(dict.fromkeys([*sample_vocabulary.cuisines, "Diner"])),
        cuisine_groups=sample_vocabulary.cuisine_groups,
        cuisine_synonyms=sample_vocabulary.cuisine_synonyms,
    )
    hybrid = RuleBasedParser(extended_vocab, semantic_matcher=_FakeSemanticMatcher())

    laptops = hybrid.parse("cheap laptops under $500")
    assert laptops.needs_clarification is not None
    assert laptops.price_range is None

    hotels = hybrid.parse("hotels in London rated above 4")
    assert hotels.needs_clarification is not None
    assert hotels.city is None

    mars = hybrid.parse("best restaurants on Mars")
    assert mars.needs_clarification is not None
    assert "Mars" in mars.needs_clarification

    romantic = hybrid.parse("romantic fancy dinner in Dubai")
    assert romantic.city == "Dubai"
    assert romantic.price_range == 4
    assert romantic.cuisine == []


def test_followup_refinement_merges_and_pivots_context(
    sample_vocabulary: VocabularySnapshot,
    test_settings: BackendSettings,
) -> None:
    from web.backend.repositories.meta_repository import MetaRepository
    from web.backend.repositories.restaurant_repository import RestaurantRepository
    from web.backend.services.search_service import merge_followup_params

    parser = RuleBasedParser(sample_vocabulary)
    t1 = parser.parse("restaurants in India")
    assert t1.country == "India"

    t2 = merge_followup_params(t1, parser.parse("in New Delhi"), "in New Delhi")
    assert t2.city == "New Delhi"
    assert t2.country is None

    t3 = merge_followup_params(
        t2,
        parser.parse("Italian rated above 4.2"),
        "Italian rated above 4.2",
    )
    assert t3.city == "New Delhi"
    assert t3.cuisine == ["Italian"]
    assert t3.min_rating == 4.2

    t4 = merge_followup_params(
        t3,
        parser.parse("with online delivery"),
        "with online delivery",
    )
    assert t4.city == "New Delhi"
    assert t4.cuisine == ["Italian"]
    assert t4.min_rating == 4.2
    assert t4.has_online_delivery is True

    t5 = merge_followup_params(
        t4,
        parser.parse("what about in London?"),
        "what about in London?",
    )
    assert t5.city == "London"
    assert t5.cuisine == ["Italian"]
    assert t5.min_rating == 4.2

    off_topic = merge_followup_params(
        t5,
        parser.parse("hotels in London rated above 4"),
        "hotels in London rated above 4",
    )
    assert off_topic.needs_clarification is not None

    service = SearchService(
        restaurant_repository=RestaurantRepository(None, test_settings),
        meta_repository=MetaRepository(None, test_settings),
        rate_limiter=SlidingWindowRateLimiter(max_requests=30),
        app_settings=test_settings,
        primary_adapter=parser,
        fallback_adapter=parser,
    )
    turn1_resp = service.search_natural_language(
        NLSearchRequest(query="restaurants in India", limit=10, offset=0),
        client_key="127.0.0.1",
    )
    assert turn1_resp.interpreted_params.country == "India"
    turn2_resp = service.search_natural_language(
        NLSearchRequest(
            query="Italian in New Delhi above 4.2",
            limit=10,
            offset=0,
            previous_params=turn1_resp.interpreted_params,
        ),
        client_key="127.0.0.1",
    )
    assert turn2_resp.interpreted_params.city == "New Delhi"
    assert turn2_resp.interpreted_params.cuisine == ["Italian"]
    assert turn2_resp.total == 1
