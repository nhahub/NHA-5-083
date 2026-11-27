"""Constrained NLP adapters (Hugging Face Inference and Rule-Based fallback)."""

from __future__ import annotations

import csv
import difflib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from huggingface_hub import InferenceClient
from pydantic import ValidationError

from web.backend.constants import (
    CITY_ALIASES,
    COUNTRY_ALIASES,
    DEFAULT_CACHE_MAX_ENTRIES,
    DEFAULT_CACHE_TTL_SECONDS,
    MAX_NLP_OUTPUT_TOKENS,
    MAX_PRICE_RANGE,
    MAX_RATING,
    MIN_PRICE_RANGE,
    MIN_RATING,
    NLP_TIMEOUT_SECONDS,
    PLACEHOLDER_PREFIX,
    PRICE_RANGE_TIER_FOUR,
    PRICE_RANGE_TIER_ONE,
    PRICE_RANGE_TIER_THREE,
    PRICE_RANGE_TIER_TWO,
    UNCONFIGURED_MODEL_MARKER,
)
from web.backend.repositories.meta_repository import VocabularySnapshot
from web.backend.schemas.nlp import SearchParams
from web.backend.services.hf_semantic_matcher import SemanticMatcher
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

PROMPT_FILE_PATH = Path(__file__).resolve().parent / "prompts" / "nl_search_prompt.txt"

_MAX_PROMPT_VOCAB_ITEMS = 120
_MIN_FUZZY_LOCATION_LEN = 5
_FUZZY_LOCATION_CUTOFF = 0.82

_DINING_DOMAIN_WORDS: frozenset[str] = frozenset(
    {
        "restaurant",
        "restaurants",
        "food",
        "eat",
        "eats",
        "dining",
        "dine",
        "cafe",
        "bistro",
        "cuisine",
        "cuisines",
        "dish",
        "dishes",
        "menu",
        "meal",
        "meals",
        "dinner",
        "lunch",
        "breakfast",
        "brunch",
    }
)

_OFF_TOPIC_KEYWORDS: frozenset[str] = frozenset(
    {
        "laptop",
        "laptops",
        "phone",
        "phones",
        "smartphone",
        "computer",
        "computers",
        "headphones",
        "hotel",
        "hotels",
        "hostel",
        "airbnb",
        "resort",
        "flight",
        "flights",
        "airline",
        "weather",
        "forecast",
        "python",
        "javascript",
        "script",
        "code",
        "engine",
        "mechanic",
        "joke",
        "jokes",
        "movie",
        "movies",
        "shoes",
    }
)

_SEMANTIC_CUISINE_STOPWORDS: frozenset[str] = frozenset(
    {
        "restaurant",
        "restaurants",
        "dinner",
        "lunch",
        "breakfast",
        "food",
        "places",
        "place",
        "spots",
        "spot",
        "eat",
        "eats",
        "dining",
        "dine",
        "meal",
        "meals",
        "best",
        "top",
        "good",
        "great",
        "nice",
        "rated",
        "rating",
        "stars",
        "star",
        "romantic",
        "fancy",
        "luxury",
        "fine",
        "cheap",
        "budget",
        "affordable",
        "moderate",
        "upscale",
        "pricey",
        "expensive",
        "inexpensive",
        "low",
        "cost",
        "price",
        "tier",
        "range",
        "with",
        "without",
        "online",
        "delivery",
        "delivers",
        "table",
        "booking",
        "reservation",
        "reservations",
        "under",
        "below",
        "above",
        "over",
        "less",
        "than",
        "max",
        "at",
        "least",
        "usd",
        "for",
        "two",
        "people",
        "in",
        "near",
        "around",
        "on",
        "the",
        "a",
        "an",
        "and",
        "or",
        "some",
        "any",
        "somewhere",
        "me",
        "find",
        "show",
        "want",
        "looking",
        "what",
        "about",
        "more",
        "only",
        "also",
        "michelin",
        "tasting",
        "menu",
        "quick",
        "bite",
    }
)

_PRICE_KEYWORD_MAP: tuple[tuple[tuple[str, ...], int], ...] = (
    (("cheap", "budget", "inexpensive", "low cost"), PRICE_RANGE_TIER_ONE),
    (("affordable", "moderate", "mid-range", "reasonable"), PRICE_RANGE_TIER_TWO),
    (("upscale", "pricey", "mid-high"), PRICE_RANGE_TIER_THREE),
    (("fine dining", "luxury", "expensive", "high-end"), PRICE_RANGE_TIER_FOUR),
)


class NLPAdapter(Protocol):
    """Protocol implemented by all natural-language search parsers."""

    def parse(self, query: str) -> SearchParams:
        """Parse a user query string into validated SearchParams."""
        ...


class NLPProviderError(RuntimeError):
    """Raised when the external NLP provider fails or returns invalid data."""


class ChatCompletionCallable(Protocol):
    """Callable protocol matching the minimal HF chat completion invocation."""

    def __call__(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Execute a chat completion and return raw assistant text."""
        ...


def load_cuisine_synonyms(cuisine_map_path: Path) -> dict[str, str]:
    """Load lowercase source_label -> canonical_cuisine mapping from CSV."""
    if not cuisine_map_path.is_file():
        return {}
    synonyms: dict[str, str] = {}
    with cuisine_map_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            src = (row.get("source_label") or "").strip().lower()
            canonical = (row.get("canonical_cuisine") or "").strip()
            if src and canonical:
                synonyms[src] = canonical
    return synonyms


def _has_any_filter(params: SearchParams) -> bool:
    """Return True if at least one concrete search criterion is populated."""
    return any(
        [
            params.country is not None,
            params.city is not None,
            params.locality is not None,
            bool(params.cuisine),
            params.cuisine_group is not None,
            params.min_rating is not None,
            params.min_cost_for_two is not None,
            params.max_cost_for_two is not None,
            params.max_cost_usd is not None,
            params.price_range is not None,
            params.has_online_delivery is not None,
            params.has_table_booking is not None,
            params.search_query is not None,
        ]
    )


def validate_against_vocabulary(
    params: SearchParams,
    vocabulary: VocabularySnapshot,
    cuisine_synonyms: dict[str, str] | None = None,
) -> SearchParams:
    """Normalize and drop extracted entities outside the known vocabulary."""
    country_lookup = {c.lower(): c for c in vocabulary.countries}
    city_lookup = {c.lower(): c for c in vocabulary.cities}
    locality_lookup = {loc.lower(): loc for loc in vocabulary.localities}
    cuisine_lookup = {c.lower(): c for c in vocabulary.cuisines}
    group_lookup = {g.lower(): g for g in vocabulary.cuisine_groups}
    synonyms = cuisine_synonyms or {}

    country: str | None = None
    if params.country:
        key = params.country.strip().lower()
        alias_target = COUNTRY_ALIASES.get(key)
        if alias_target and alias_target.lower() in country_lookup:
            country = country_lookup[alias_target.lower()]
        else:
            country = country_lookup.get(key)

    city = city_lookup.get(params.city.strip().lower()) if params.city else None
    locality = (
        locality_lookup.get(params.locality.strip().lower())
        if params.locality
        else None
    )
    cuisine_group = (
        group_lookup.get(params.cuisine_group.strip().lower())
        if params.cuisine_group
        else None
    )

    normalized_cuisines: list[str] = []
    seen_cuisines: set[str] = set()
    for raw_cuisine in params.cuisine:
        c_key = raw_cuisine.strip().lower()
        canonical = cuisine_lookup.get(c_key)
        if canonical is None and c_key in synonyms:
            syn_target = synonyms[c_key].lower()
            canonical = cuisine_lookup.get(syn_target, synonyms[c_key])
        if canonical is not None and canonical not in seen_cuisines:
            seen_cuisines.add(canonical)
            normalized_cuisines.append(canonical)

    validated = params.model_copy(
        update={
            "country": country,
            "city": city,
            "locality": locality,
            "cuisine": normalized_cuisines,
            "cuisine_group": cuisine_group,
        }
    )
    if not _has_any_filter(validated) and validated.needs_clarification is None:
        validated = validated.model_copy(
            update={
                "needs_clarification": (
                    "Could not match known locations or cuisines. "
                    "Try specifying a city, country, cuisine, or minimum rating."
                )
            }
        )
    return validated


class RuleBasedParser:
    """Deterministic regex and vocabulary-based natural-language parser."""

    def __init__(
        self,
        vocabulary: VocabularySnapshot,
        cuisine_synonyms: dict[str, str] | None = None,
        semantic_matcher: SemanticMatcher | None = None,
    ) -> None:
        """Initialize the rule-based parser with vocabulary, synonyms, and matcher."""
        self._vocabulary = vocabulary
        self._synonyms = cuisine_synonyms or {}
        self._semantic_matcher = semantic_matcher

    @property
    def has_active_semantic_matcher(self) -> bool:
        """Return True when an initialized semantic matcher is attached."""
        return bool(self._semantic_matcher and self._semantic_matcher.is_ready())

    @staticmethod
    def _match_whole_word(
        text_lower: str,
        candidates: list[str],
    ) -> str | None:
        """Return the longest whole-word case-insensitive match from candidates."""
        for candidate in sorted(candidates, key=len, reverse=True):
            if not candidate:
                continue
            pattern = rf"(?<!\w){re.escape(candidate.lower())}(?!\w)"
            if re.search(pattern, text_lower):
                return candidate
        return None

    def _extract_country(self, text_lower: str) -> str | None:
        """Extract canonical country name or recognized alias."""
        direct = self._match_whole_word(text_lower, list(self._vocabulary.countries))
        if direct is not None:
            return direct
        alias_match = self._match_whole_word(text_lower, list(COUNTRY_ALIASES.keys()))
        if alias_match is not None:
            canonical = COUNTRY_ALIASES[alias_match.lower()]
            if canonical in self._vocabulary.countries:
                return canonical
        return None

    def _extract_city(self, text_lower: str) -> str | None:
        """Extract canonical city name or recognized alias."""
        direct = self._match_whole_word(text_lower, list(self._vocabulary.cities))
        if direct is not None:
            return direct
        alias_match = self._match_whole_word(text_lower, list(CITY_ALIASES.keys()))
        if alias_match is not None:
            canonical = CITY_ALIASES[alias_match.lower()]
            if canonical in self._vocabulary.cities:
                return canonical
        return None

    def _fuzzy_match_location(
        self,
        candidate: str,
    ) -> tuple[str | None, str | None]:
        """Recover minor typos in explicit location names via difflib."""
        cand_lower = candidate.strip().lower()
        if len(cand_lower) < _MIN_FUZZY_LOCATION_LEN:
            return None, None
        city_map = {c.lower(): c for c in self._vocabulary.cities}
        for alias, canonical in CITY_ALIASES.items():
            if canonical in self._vocabulary.cities:
                city_map[alias] = canonical
        city_hits = difflib.get_close_matches(
            cand_lower, list(city_map.keys()), n=1, cutoff=_FUZZY_LOCATION_CUTOFF
        )
        if city_hits:
            return None, city_map[city_hits[0]]
        country_map = {c.lower(): c for c in self._vocabulary.countries}
        country_hits = difflib.get_close_matches(
            cand_lower, list(country_map.keys()), n=1, cutoff=_FUZZY_LOCATION_CUTOFF
        )
        if country_hits:
            return country_map[country_hits[0]], None
        return None, None

    @staticmethod
    def _spans_overlap(
        span: tuple[int, int],
        occupied_spans: list[tuple[int, int]],
    ) -> bool:
        """Return True if candidate [start, end) overlaps any occupied span."""
        start, end = span
        return any(
            start < occ_end and end > occ_start for occ_start, occ_end in occupied_spans
        )

    def _extract_cuisines(self, text_lower: str) -> list[str]:
        """Extract canonical cuisines from vocabulary and known synonyms.

        Matches longest candidates first and records character spans so shorter
        sub-phrases (e.g., ``Indian`` inside ``North Indian``) are not emitted
        as duplicate OR-filters in SQL search.

        Args:
            text_lower: Lowercased user query string.

        Returns:
            Ordered list of unique canonical cuisine names found in the query.
        """
        found: list[str] = []
        seen: set[str] = set()
        occupied_spans: list[tuple[int, int]] = []
        # Longest-first span tracking stops "North Indian" from also matching "Indian".
        for cuisine in sorted(self._vocabulary.cuisines, key=len, reverse=True):
            pattern = rf"(?<!\w){re.escape(cuisine.lower())}(?!\w)"
            match = re.search(pattern, text_lower)
            if match and not self._spans_overlap(match.span(), occupied_spans):
                occupied_spans.append(match.span())
                if cuisine not in seen:
                    seen.add(cuisine)
                    found.append(cuisine)
        for alias, canonical in sorted(
            self._synonyms.items(), key=lambda pair: len(pair[0]), reverse=True
        ):
            pattern = rf"(?<!\w){re.escape(alias)}(?!\w)"
            match = re.search(pattern, text_lower)
            if (
                match
                and not self._spans_overlap(match.span(), occupied_spans)
                and canonical in self._vocabulary.cuisines
            ):
                occupied_spans.append(match.span())
                if canonical not in seen:
                    seen.add(canonical)
                    found.append(canonical)
        return found

    def _extract_unmatched_location(
        self,
        raw_query: str,
        text_lower: str,
    ) -> str | None:
        """Detect an explicit location preposition phrase absent from vocabulary.

        Used only when exact country, city, and locality matching all failed so
        out-of-catalog places (e.g., ``in Cairo`` or ``on Mars``) trigger a
        clarification instead of silently returning worldwide venues.

        Args:
            raw_query: Original user query preserving casing for error messages.
            text_lower: Lowercased copy of ``raw_query``.

        Returns:
            The unmatched location phrase if detected, otherwise ``None``.
        """
        stop_pattern = (
            r"\b(?:with|without|under|below|max|less|above|over|rated|rating|"
            r"price|tier|for|and|or|delivers|delivery|booking|reservations?|"
            r"food|cuisine|cuisines|restaurant|restaurants)\b|\d|\$"
        )
        non_location_words = {
            "budget",
            "affordable",
            "moderate",
            "cheap",
            "inexpensive",
            "upscale",
            "pricey",
            "expensive",
            "luxury",
            "fine",
            "dining",
            "style",
            "mood",
            "general",
            "town",
            "person",
            "advance",
            "the",
            "a",
            "an",
            "any",
            "all",
            "my",
            "home",
            "night",
            "menu",
            "line",
            "time",
            "hand",
            "site",
            "offer",
            "sale",
        }
        # Negative lookahead avoids treating "at least 4 stars" as a place name.
        for match in re.finditer(
            r"\b(?:in|near|around|on|at(?!\s+least\b))\s+([^,;?.!]+)",
            text_lower,
        ):
            start_offset = match.start(1)
            fragment_lower = match.group(1)
            stop_match = re.search(stop_pattern, fragment_lower)
            end_offset = (
                start_offset + stop_match.start() if stop_match else match.end(1)
            )
            candidate = raw_query[start_offset:end_offset].strip(" \t\r\n.,;:-")
            if not candidate:
                continue
            words = [w.lower() for w in re.findall(r"[a-z]+", candidate)]
            if not words or all(word in non_location_words for word in words):
                continue
            if self._extract_cuisines(candidate.lower()):
                continue
            return candidate
        return None

    @staticmethod
    def _extract_rating(text_lower: str) -> float | None:
        """Extract minimum rating filter from natural language."""
        patterns = (
            r"(?:rating\s*(?:above|over|at least|>=|>|=)?\s*)(\d(?:\.\d)?)",
            r"(?:above|over|at least|>=|>)\s*(\d(?:\.\d)?)\s*(?:stars?|rating)?",
            r"(\d(?:\.\d)?)\s*\+\s*(?:stars?|rating)",
            r"(\d(?:\.\d)?)\s*stars?",
        )
        for pattern in patterns:
            match = re.search(pattern, text_lower)
            if match:
                val = float(match.group(1))
                if MIN_RATING <= val <= MAX_RATING:
                    return val
        return None

    @staticmethod
    def _extract_costs(
        text_lower: str,
    ) -> tuple[float | None, float | None]:
        """Extract USD or local-currency cost ceilings."""
        usd_pattern = (
            r"(?:under|below|max|less than|<=)\s*"
            r"(?:\$\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*usd\b)"
        )
        usd_match = re.search(usd_pattern, text_lower)
        if usd_match:
            raw_num = usd_match.group(1) or usd_match.group(2)
            return None, float(raw_num)

        local_pattern = (
            r"(?:under|below|max|less than|<=)\s*"
            r"(\d+(?:\.\d+)?)(?!\s*(?:stars?|rating|%))"
        )
        local_match = re.search(local_pattern, text_lower)
        if local_match:
            return float(local_match.group(1)), None
        return None, None

    @staticmethod
    def _extract_price_range(text_lower: str) -> int | None:
        """Extract explicit price tier or affordability keywords."""
        explicit = re.search(
            r"(?:price\s*(?:range|tier)|tier)\s*([1-4])\b",
            text_lower,
        )
        if explicit:
            tier = int(explicit.group(1))
            if MIN_PRICE_RANGE <= tier <= MAX_PRICE_RANGE:
                return tier
        for keywords, tier in _PRICE_KEYWORD_MAP:
            for keyword in keywords:
                if re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text_lower):
                    return tier
        return None

    @staticmethod
    def _clean_for_semantic_cuisine(semantic_query: str) -> str:
        """Strip generic meal, filler, and price tokens before cuisine lookup."""
        tokens = re.findall(r"[a-zA-Z]+", semantic_query.lower())
        kept = [tok for tok in tokens if tok not in _SEMANTIC_CUISINE_STOPWORDS]
        return " ".join(kept)

    def _is_off_topic_query(
        self,
        query: str,
        text_lower: str,
        matched_cuisines: list[str],
    ) -> bool:
        """Return True if the query is clearly unrelated to restaurants/dining."""
        if matched_cuisines:
            return False
        words = set(re.findall(r"[a-z]+", text_lower))
        if words.intersection(_DINING_DOMAIN_WORDS):
            return False
        if words.intersection(_OFF_TOPIC_KEYWORDS):
            return True
        return bool(
            self._semantic_matcher is not None
            and self._semantic_matcher.is_ready()
            and self._semantic_matcher.is_off_topic(query)
        )

    def parse(self, query: str) -> SearchParams:
        """Parse a user query into validated ``SearchParams``.

        Applies deterministic extraction first (domain gate, locations,
        cuisines, ratings, budgets, booleans), then enriches unmatched dish or
        price-tier intent through the optional local HF ONNX semantic matcher.

        Args:
            query: Raw natural-language prompt from the user.

        Returns:
            Validated ``SearchParams`` constrained to known vocabulary values.
        """
        text_lower = query.lower()
        cuisines = self._extract_cuisines(text_lower)
        # Reject non-dining prompts before extracting generic budget/city tokens.
        if self._is_off_topic_query(query, text_lower, cuisines):
            return SearchParams(
                needs_clarification=(
                    "EatoSphere only searches restaurants and dining spots. "
                    "Try specifying a cuisine, city, rating, or budget "
                    "(e.g., 'Italian in Mumbai under $30')."
                )
            )

        country = self._extract_country(text_lower)
        city = self._extract_city(text_lower)
        locality = self._match_whole_word(text_lower, list(self._vocabulary.localities))
        if locality and city and locality.lower() == city.lower():
            locality = None

        # Only attempt fuzzy typo recovery on explicit location clauses when exact
        # lookups miss, keeping short/unrelated words (e.g. "Mars") unmatched.
        unknown_location: str | None = None
        if country is None and city is None and locality is None:
            unknown_location = self._extract_unmatched_location(query, text_lower)
            if unknown_location is not None:
                fuzzy_country, fuzzy_city = self._fuzzy_match_location(unknown_location)
                if fuzzy_country is not None or fuzzy_city is not None:
                    country = fuzzy_country
                    city = fuzzy_city
                    unknown_location = None

        cuisine_group = (
            None
            if cuisines
            else self._match_whole_word(
                text_lower, list(self._vocabulary.cuisine_groups)
            )
        )
        min_rating = self._extract_rating(text_lower)
        max_cost_for_two, max_cost_usd = self._extract_costs(text_lower)
        price_range = self._extract_price_range(text_lower)

        if (
            unknown_location is None
            and self._semantic_matcher is not None
            and self._semantic_matcher.is_ready()
        ):
            # Strip matched locations so city names (e.g. "Dubai") do not bias
            # semantic cuisine embeddings toward regional cuisines.
            semantic_query = query
            for loc_token in (country, city, locality):
                if loc_token:
                    semantic_query = re.sub(
                        rf"\b(?:in|near|around|on|at)?\s*{re.escape(loc_token)}\b",
                        " ",
                        semantic_query,
                        flags=re.IGNORECASE,
                    )
            semantic_query = " ".join(semantic_query.split())
            if not cuisines and cuisine_group is None:
                # Strip meal/vibe words so "fancy dinner" does not match "Diner".
                cuisine_query = self._clean_for_semantic_cuisine(semantic_query)
                if cuisine_query:
                    cuisines = self._semantic_matcher.match_cuisines(cuisine_query)
            if (
                price_range is None
                and max_cost_for_two is None
                and max_cost_usd is None
            ):
                price_range = self._semantic_matcher.match_price_range(semantic_query)

        has_online_delivery: bool | None = None
        if re.search(r"\b(?:no|without)\s+(?:online\s+)?delivery\b", text_lower):
            has_online_delivery = False
        elif re.search(
            r"\b(?:online\s+delivery|with\s+delivery|delivers)\b",
            text_lower,
        ):
            has_online_delivery = True

        has_table_booking: bool | None = None
        if re.search(
            r"\b(?:no|without)\s+(?:table\s+booking|reservations?)\b", text_lower
        ):
            has_table_booking = False
        elif re.search(
            r"\b(?:table\s+booking|book\s+a\s+table|reservations?)\b", text_lower
        ):
            has_table_booking = True

        params = SearchParams(
            country=country,
            city=city,
            locality=locality,
            cuisine=cuisines,
            cuisine_group=cuisine_group,
            min_rating=min_rating,
            max_cost_for_two=max_cost_for_two,
            max_cost_usd=max_cost_usd,
            price_range=price_range,
            has_online_delivery=has_online_delivery,
            has_table_booking=has_table_booking,
        )
        if unknown_location is not None:
            params = params.model_copy(
                update={
                    "needs_clarification": (
                        f"Location '{unknown_location}' was not found in the "
                        "catalog. Try a supported country or city (e.g., "
                        "New Delhi, Mumbai, London, Dubai, or Singapore)."
                    )
                }
            )
        if not _has_any_filter(params) and params.needs_clarification is None:
            params = params.model_copy(
                update={
                    "needs_clarification": (
                        "I could not match a known city, country, cuisine, or budget. "
                        "Try e.g. 'Italian in New Delhi above 4.2 under 1500'."
                    )
                }
            )
        return validate_against_vocabulary(params, self._vocabulary, self._synonyms)


class HuggingFaceAdapter:
    """Constrained NLP adapter backed by Hugging Face Inference Providers."""

    def __init__(
        self,
        vocabulary: VocabularySnapshot,
        cuisine_synonyms: dict[str, str] | None = None,
        app_settings: BackendSettings | None = None,
        completion_fn: ChatCompletionCallable | None = None,
        clock: Callable[[], float] = time.monotonic,
        prompt_path: Path = PROMPT_FILE_PATH,
    ) -> None:
        """Initialize the Hugging Face adapter, prompt template, and TTL cache."""
        self._vocabulary = vocabulary
        self._synonyms = cuisine_synonyms or {}
        self._settings = app_settings or settings
        self._completion_fn = completion_fn
        self._clock = clock
        self._prompt_template = prompt_path.read_text(encoding="utf-8")
        self._cache_lock = threading.Lock()
        self._cache: OrderedDict[str, tuple[float, SearchParams]] = OrderedDict()

    def is_configured(self) -> bool:
        """Return True if a non-placeholder HF key and model ID are configured."""
        if self._completion_fn is not None:
            return True
        api_key = self._settings.hf_api_key.get_secret_value().strip()
        model_id = self._settings.nlp_model_id.strip()
        return (
            bool(api_key)
            and not api_key.startswith(PLACEHOLDER_PREFIX)
            and bool(model_id)
            and not model_id.startswith(UNCONFIGURED_MODEL_MARKER)
        )

    def _get_cached(self, cache_key: str) -> SearchParams | None:
        """Return non-expired cached SearchParams if present."""
        now = self._clock()
        ttl = float(
            min(
                self._settings.nlp_cache_ttl_seconds,
                DEFAULT_CACHE_TTL_SECONDS,
            )
            if self._settings.nlp_cache_ttl_seconds <= 0
            else self._settings.nlp_cache_ttl_seconds
        )
        with self._cache_lock:
            entry = self._cache.get(cache_key)
            if entry is None:
                return None
            stored_at, params = entry
            if now - stored_at > ttl:
                self._cache.pop(cache_key, None)
                return None
            self._cache.move_to_end(cache_key)
            return params

    def _put_cached(self, cache_key: str, params: SearchParams) -> None:
        """Insert parsed SearchParams into the bounded LRU+TTL cache."""
        max_entries = max(
            1,
            self._settings.nlp_cache_max_entries or DEFAULT_CACHE_MAX_ENTRIES,
        )
        with self._cache_lock:
            if cache_key in self._cache:
                self._cache.move_to_end(cache_key)
            self._cache[cache_key] = (self._clock(), params)
            while len(self._cache) > max_entries:
                self._cache.popitem(last=False)

    def _build_system_prompt(self) -> str:
        """Render the versioned prompt template with known vocabulary slices."""
        return self._prompt_template.format(
            countries=list(self._vocabulary.countries),
            cities=list(self._vocabulary.cities[:_MAX_PROMPT_VOCAB_ITEMS]),
            cuisines=list(self._vocabulary.cuisines[:_MAX_PROMPT_VOCAB_ITEMS]),
            cuisine_groups=list(self._vocabulary.cuisine_groups),
        )

    def _call_provider(self, query: str) -> str:
        """Call the Hugging Face Inference chat completion endpoint."""
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": query},
        ]
        timeout_seconds = min(
            self._settings.nlp_timeout_seconds,
            NLP_TIMEOUT_SECONDS,
        )
        max_tokens = min(
            self._settings.nlp_max_output_tokens,
            MAX_NLP_OUTPUT_TOKENS,
        )
        temperature = 0.0

        if self._completion_fn is not None:
            return self._completion_fn(
                model=self._settings.nlp_model_id,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        api_key = self._settings.hf_api_key.get_secret_value()
        provider = self._settings.nlp_provider.strip()
        if provider and not provider.startswith(UNCONFIGURED_MODEL_MARKER):
            client = InferenceClient(
                api_key=api_key,
                timeout=float(timeout_seconds),
                provider=provider,  # type: ignore[arg-type]
            )
        else:
            client = InferenceClient(
                api_key=api_key,
                timeout=float(timeout_seconds),
            )
        response = client.chat.completions.create(
            model=self._settings.nlp_model_id,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        if not content:
            raise NLPProviderError("Empty response from Hugging Face provider")
        return str(content)

    @staticmethod
    def _extract_json_payload(raw_text: str) -> SearchParams:
        """Strip reasoning tags and validate raw JSON against SearchParams."""
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise NLPProviderError("No JSON object found in model output")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise NLPProviderError("Malformed JSON returned by model") from exc
        if not isinstance(payload, dict):
            raise NLPProviderError("Model output JSON must be an object")
        try:
            return SearchParams.model_validate(payload)
        except ValidationError as exc:
            raise NLPProviderError("Model JSON failed SearchParams validation") from exc

    def parse(self, query: str) -> SearchParams:
        """Parse a user query via Hugging Face Inference with caching and validation."""
        if not self.is_configured():
            raise NLPProviderError("Hugging Face provider is not configured")

        cache_key = query.strip().lower()
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            raw_output = self._call_provider(query)
        except NLPProviderError:
            raise
        except Exception as exc:
            raise NLPProviderError(
                f"Hugging Face inference failed: {type(exc).__name__}"
            ) from exc

        parsed = self._extract_json_payload(raw_output)
        validated = validate_against_vocabulary(
            parsed, self._vocabulary, self._synonyms
        )
        self._put_cached(cache_key, validated)
        return validated
