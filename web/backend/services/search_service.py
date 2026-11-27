"""Orchestration service for rate-limited natural-language restaurant search."""

from __future__ import annotations

import logging
import re
from typing import Literal

from web.backend.constants import QUERY_LOG_MAX_CHARS
from web.backend.logging_config import truncate_query_for_log
from web.backend.repositories.meta_repository import MetaRepository
from web.backend.repositories.restaurant_repository import (
    RestaurantFilter,
    RestaurantRepository,
)
from web.backend.schemas.nlp import (
    NLSearchRequest,
    NLSearchResponseOut,
    SearchParams,
)
from web.backend.services.hf_semantic_matcher import get_cached_semantic_matcher
from web.backend.services.nlp_adapter import (
    HuggingFaceAdapter,
    NLPAdapter,
    NLPProviderError,
    RuleBasedParser,
    load_cuisine_synonyms,
)
from web.backend.services.rate_limiter import SlidingWindowRateLimiter
from web.backend.settings import BackendSettings, settings

logger = logging.getLogger(__name__)

_RESET_CONTEXT_PATTERN = re.compile(
    r"\b(?:start\s+over|reset|new\s+search|clear\s+filters?)\b",
    flags=re.IGNORECASE,
)


def merge_followup_params(
    previous: SearchParams,
    current: SearchParams,
    query: str,
) -> SearchParams:
    """Merge follow-up ``SearchParams`` onto previous active search context.

    Preserves statelessness across API replicas by accepting the client's prior
    ``SearchParams``. Clarifications (off-topic or unknown locations) and
    explicit reset phrases bypass merging so errors are never masked by stale
    filters.

    Args:
        previous: Active ``SearchParams`` from the prior conversation turn.
        current: Newly parsed ``SearchParams`` from the follow-up prompt.
        query: Raw follow-up query text checked for explicit reset phrases.

    Returns:
        Merged ``SearchParams`` with location-hierarchy and currency conflicts
        resolved.
    """
    if current.needs_clarification is not None or _RESET_CONTEXT_PATTERN.search(query):
        return current

    country = previous.country
    city = previous.city
    locality = previous.locality

    if current.country is not None:
        # Changing country invalidates any narrower city/locality from the prior turn.
        if previous.country and current.country.lower() != previous.country.lower():
            city = None
            locality = None
        country = current.country

    if current.city is not None:
        if previous.city and current.city.lower() != previous.city.lower():
            locality = None
        # Clear inherited country when pivoting cities (e.g. India -> "in London")
        # so an old country filter cannot zero out results for the new city.
        if current.country is None:
            country = None
        city = current.city

    if current.locality is not None:
        locality = current.locality

    if current.cuisine:
        cuisine = list(current.cuisine)
        cuisine_group = None
    elif current.cuisine_group is not None:
        cuisine = []
        cuisine_group = current.cuisine_group
    else:
        cuisine = list(previous.cuisine)
        cuisine_group = previous.cuisine_group

    if current.max_cost_usd is not None:
        max_cost_usd: float | None = current.max_cost_usd
        max_cost_for_two: float | None = None
    elif current.max_cost_for_two is not None:
        max_cost_usd = None
        max_cost_for_two = current.max_cost_for_two
    else:
        max_cost_usd = previous.max_cost_usd
        max_cost_for_two = previous.max_cost_for_two

    return SearchParams(
        country=country,
        city=city,
        locality=locality,
        cuisine=cuisine,
        cuisine_group=cuisine_group,
        min_rating=(
            current.min_rating
            if current.min_rating is not None
            else previous.min_rating
        ),
        min_cost_for_two=(
            current.min_cost_for_two
            if current.min_cost_for_two is not None
            else previous.min_cost_for_two
        ),
        max_cost_for_two=max_cost_for_two,
        max_cost_usd=max_cost_usd,
        price_range=(
            current.price_range
            if current.price_range is not None
            else previous.price_range
        ),
        has_online_delivery=(
            current.has_online_delivery
            if current.has_online_delivery is not None
            else previous.has_online_delivery
        ),
        has_table_booking=(
            current.has_table_booking
            if current.has_table_booking is not None
            else previous.has_table_booking
        ),
        search_query=(
            current.search_query
            if current.search_query is not None
            else previous.search_query
        ),
        needs_clarification=None,
    )


class SearchService:
    """Service coordinating NLP parsing, fallback, logging, and DB search."""

    def __init__(
        self,
        restaurant_repository: RestaurantRepository,
        meta_repository: MetaRepository,
        rate_limiter: SlidingWindowRateLimiter,
        app_settings: BackendSettings | None = None,
        primary_adapter: NLPAdapter | None = None,
        fallback_adapter: NLPAdapter | None = None,
    ) -> None:
        """Initialize SearchService with repositories, limiter, and NLP adapters."""
        self._restaurant_repository = restaurant_repository
        self._meta_repository = meta_repository
        self._rate_limiter = rate_limiter
        self._settings = app_settings or settings
        self._primary_adapter = primary_adapter
        self._fallback_adapter = fallback_adapter

    def _resolve_adapters(self) -> tuple[NLPAdapter, NLPAdapter]:
        """Build or return primary and fallback NLP adapters using live vocabulary."""
        if self._primary_adapter is not None and self._fallback_adapter is not None:
            return self._primary_adapter, self._fallback_adapter

        vocabulary = self._meta_repository.get_vocabulary()
        synonyms = load_cuisine_synonyms(self._settings.cuisine_map_path)
        semantic_matcher = get_cached_semantic_matcher(vocabulary, self._settings)
        fallback = self._fallback_adapter or RuleBasedParser(
            vocabulary=vocabulary,
            cuisine_synonyms=synonyms,
            semantic_matcher=semantic_matcher,
        )
        primary = self._primary_adapter or HuggingFaceAdapter(
            vocabulary=vocabulary,
            cuisine_synonyms=synonyms,
            app_settings=self._settings,
        )
        return primary, fallback

    def search_natural_language(
        self,
        request_payload: NLSearchRequest,
        client_key: str,
    ) -> NLSearchResponseOut:
        """Rate-limit, parse, log safely, and execute a natural-language search."""
        self._rate_limiter.check_and_record(client_key)

        primary_adapter, fallback_adapter = self._resolve_adapters()
        parser_used: Literal["huggingface", "huggingface_semantic", "rule_based"] = (
            "huggingface"
        )
        fallback_used = False
        interpreted_params: SearchParams

        if isinstance(primary_adapter, RuleBasedParser):
            interpreted_params = primary_adapter.parse(request_payload.query)
            parser_used = (
                "huggingface_semantic"
                if primary_adapter.has_active_semantic_matcher
                else "rule_based"
            )
            fallback_used = False
        else:
            try:
                interpreted_params = primary_adapter.parse(request_payload.query)
            except (NLPProviderError, TimeoutError, ValueError, RuntimeError) as exc:
                semantic_active = (
                    isinstance(fallback_adapter, RuleBasedParser)
                    and fallback_adapter.has_active_semantic_matcher
                )
                parser_used = (
                    "huggingface_semantic" if semantic_active else "rule_based"
                )
                logger.warning(
                    "Primary NLP parser failed; falling back to local parser",
                    extra={
                        "parser_used": parser_used,
                        "fallback_used": True,
                        "details": str(exc)[:QUERY_LOG_MAX_CHARS],
                    },
                )
                interpreted_params = fallback_adapter.parse(request_payload.query)
                fallback_used = True

        truncated_query = truncate_query_for_log(
            request_payload.query,
            max_chars=self._settings.logging_query_max_chars,
        )
        logger.info(
            "Processed natural-language search query",
            extra={
                "parser_used": parser_used,
                "fallback_used": fallback_used,
                "query_preview": truncated_query,
            },
        )

        if request_payload.previous_params is not None:
            interpreted_params = merge_followup_params(
                request_payload.previous_params,
                interpreted_params,
                request_payload.query,
            )

        if interpreted_params.needs_clarification is not None:
            return NLSearchResponseOut(
                query=request_payload.query,
                interpreted_params=interpreted_params,
                parser_used=parser_used,
                fallback_used=fallback_used,
                items=[],
                total=0,
                limit=request_payload.limit,
                offset=request_payload.offset,
            )

        criteria = RestaurantFilter(
            country=interpreted_params.country,
            city=interpreted_params.city,
            locality=interpreted_params.locality,
            cuisine=tuple(interpreted_params.cuisine),
            cuisine_group=interpreted_params.cuisine_group,
            min_rating=interpreted_params.min_rating,
            max_cost_for_two=interpreted_params.max_cost_for_two,
            max_cost_usd=interpreted_params.max_cost_usd,
            price_range=interpreted_params.price_range,
            has_online_delivery=interpreted_params.has_online_delivery,
            has_table_booking=interpreted_params.has_table_booking,
            search_query=interpreted_params.search_query,
            sort_by="rating",
            limit=request_payload.limit,
            offset=request_payload.offset,
        )
        items, total = self._restaurant_repository.search_restaurants(criteria)
        return NLSearchResponseOut(
            query=request_payload.query,
            interpreted_params=interpreted_params,
            parser_used=parser_used,
            fallback_used=fallback_used,
            items=items,
            total=total,
            limit=request_payload.limit,
            offset=request_payload.offset,
        )
