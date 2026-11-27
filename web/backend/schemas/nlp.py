"""Natural-language search request, extracted filter, and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from web.backend.constants import (
    DEFAULT_PAGE_LIMIT,
    MAX_NLP_INPUT_CHARS,
    MAX_PAGE_LIMIT,
    MAX_PRICE_RANGE,
    MAX_RATING,
    MIN_COST,
    MIN_PAGE_LIMIT,
    MIN_PRICE_RANGE,
    MIN_RATING,
)
from web.backend.schemas.restaurant import RestaurantOut


class SearchParams(BaseModel):
    """Constrained search parameters extracted from natural language."""

    model_config = ConfigDict(extra="forbid")

    country: str | None = None
    city: str | None = None
    locality: str | None = None
    cuisine: list[str] = Field(default_factory=list)
    cuisine_group: str | None = None
    min_rating: float | None = Field(default=None, ge=MIN_RATING, le=MAX_RATING)
    min_cost_for_two: float | None = Field(default=None, ge=MIN_COST)
    max_cost_for_two: float | None = Field(default=None, ge=MIN_COST)
    max_cost_usd: float | None = Field(default=None, ge=MIN_COST)
    price_range: int | None = Field(
        default=None, ge=MIN_PRICE_RANGE, le=MAX_PRICE_RANGE
    )
    has_online_delivery: bool | None = None
    has_table_booking: bool | None = None
    search_query: str | None = None
    needs_clarification: str | None = None


SearchParamsOut = SearchParams


class NLSearchRequest(BaseModel):
    """Request payload for POST /api/search/nl."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=MAX_NLP_INPUT_CHARS)
    limit: int = Field(default=DEFAULT_PAGE_LIMIT, ge=MIN_PAGE_LIMIT, le=MAX_PAGE_LIMIT)
    offset: int = Field(default=0, ge=0)
    previous_params: SearchParams | None = None

    @field_validator("query")
    @classmethod
    def validate_non_blank_query(cls, value: str) -> str:
        """Ensure the query contains at least one non-whitespace character."""
        if not value.strip():
            raise ValueError("query must not be blank")
        return value.strip()


class NLSearchResponseOut(BaseModel):
    """Response payload for POST /api/search/nl."""

    query: str
    interpreted_params: SearchParamsOut
    parser_used: Literal["huggingface", "huggingface_semantic", "rule_based"]
    fallback_used: bool
    items: list[RestaurantOut]
    total: int
    limit: int
    offset: int
