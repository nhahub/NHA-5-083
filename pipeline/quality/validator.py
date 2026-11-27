"""Record-level validation and standardization for the Zomato Silver pipeline."""

import logging
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd

from pipeline.constants import (
    COUNTRY_CODE_TO_METADATA,
    DEFAULT_LOCALITY_FALLBACK,
    MAX_VARCHAR_ADDRESS,
    MAX_VARCHAR_CITY,
    MAX_VARCHAR_LOCALITY,
    MAX_VARCHAR_NAME,
    MAX_VARCHAR_RATING_COLOR,
    MAX_VARCHAR_RATING_TEXT,
    MAX_VARCHAR_REASON,
    MAX_VARCHAR_SOURCE_RECORD_ID,
    MIN_VOTES,
    RULE_BOOLEAN_FLAG_INVALID,
    RULE_CITY_MISSING,
    RULE_COORDINATES_MISSING,
    RULE_COORDINATES_OUT_OF_RANGE,
    RULE_COST_NEGATIVE,
    RULE_COST_ZERO,
    RULE_COUNTRY_CODE_UNKNOWN,
    RULE_CUISINE_MISSING,
    RULE_CUISINE_UNMAPPED,
    RULE_CURRENCY_LABEL_MISMATCH,
    RULE_NAME_MISSING,
    RULE_PRICE_RANGE_INVALID,
    RULE_RATING_OUT_OF_RANGE,
    RULE_SOURCE_ID_DUPLICATE_IN_BATCH,
    RULE_SOURCE_ID_MISSING,
    RULE_TEXT_MOJIBAKE_REPAIRED,
    RULE_VOTES_NEGATIVE,
    SEVERITY_REJECT,
    SEVERITY_WARNING,
)
from pipeline.settings import PipelineRuntimeConfig
from pipeline.transform.cuisines import CuisineVocabulary, normalize_cuisines
from pipeline.transform.currency import resolve_country_currency
from pipeline.transform.standardize import (
    StandardizedRestaurant,
    compute_record_hash,
    parse_boolean_flag,
    parse_coordinates,
    parse_cost,
    parse_rating,
    repair_text,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityIssue:
    """Single reject or warning event destined for ``data_quality_issues``."""

    source_record_id: str | None
    rule_name: str
    severity: str
    reason: str
    raw_payload: dict[str, str]
    detected_at: datetime


@dataclass(frozen=True)
class RejectedRecord:
    """Quarantined record with its primary rejection rule and raw payload."""

    source_record_id: str | None
    rule_name: str
    reason: str
    raw_payload: dict[str, str]


@dataclass(frozen=True)
class ValidationResult:
    """Complete output of validating and standardizing one batch."""

    records_read: int
    valid_records: list[StandardizedRestaurant]
    rejected_records: list[RejectedRecord]
    issues: list[QualityIssue]
    rows_warned: int


def _to_raw_payload(row: Mapping[object, object]) -> dict[str, str]:
    return {str(key): "" if val is None else str(val) for key, val in row.items()}


def _find_duplicate_source_ids(raw_df: pd.DataFrame) -> set[str]:
    counts: Counter[str] = Counter()
    for raw_val in raw_df["Restaurant ID"].to_list():
        cleaned = "" if raw_val is None else str(raw_val).strip()
        if cleaned.isdigit():
            counts[cleaned] += 1
    return {source_id for source_id, count in counts.items() if count > 1}


def _parse_votes(raw_votes: str) -> int | None:
    cleaned = raw_votes.strip()
    if not cleaned:
        return MIN_VOTES
    try:
        parsed = int(cleaned)
    except ValueError:
        return None
    if parsed < MIN_VOTES:
        return None
    return parsed


def _parse_price_range(raw_price_range: str, min_pr: int, max_pr: int) -> int | None:
    cleaned = raw_price_range.strip()
    if not cleaned:
        return None
    try:
        parsed = int(cleaned)
    except ValueError:
        return None
    if parsed < min_pr or parsed > max_pr:
        return None
    return parsed


def _evaluate_reject_rules(
    payload: dict[str, str],
    duplicate_ids: set[str],
    config: PipelineRuntimeConfig,
) -> tuple[list[tuple[str, str]], dict[str, object]]:
    """Evaluate all reject-severity rules for one row."""
    failures: list[tuple[str, str]] = []
    parsed: dict[str, object] = {}

    raw_id = payload.get("Restaurant ID", "").strip()
    if not raw_id or not raw_id.isdigit():
        failures.append(
            (RULE_SOURCE_ID_MISSING, "source restaurant id missing or not numeric")
        )
    else:
        if raw_id in duplicate_ids:
            failures.append(
                (
                    RULE_SOURCE_ID_DUPLICATE_IN_BATCH,
                    "duplicate source restaurant id in batch",
                )
            )
        parsed["source_restaurant_id"] = raw_id[:MAX_VARCHAR_SOURCE_RECORD_ID]

    name_clean, name_repaired = repair_text(
        payload.get("Restaurant Name", ""), max_length=MAX_VARCHAR_NAME
    )
    if not name_clean:
        failures.append((RULE_NAME_MISSING, "restaurant name missing"))
    parsed["name"] = name_clean
    parsed["name_repaired"] = name_repaired

    raw_country = payload.get("Country Code", "").strip()
    country_code: int | None = None
    if raw_country.isdigit():
        candidate_cc = int(raw_country)
        if candidate_cc in COUNTRY_CODE_TO_METADATA:
            country_code = candidate_cc
    if country_code is None:
        failures.append((RULE_COUNTRY_CODE_UNKNOWN, "unknown country code"))
    parsed["country_code"] = country_code

    city_clean, city_repaired = repair_text(
        payload.get("City", ""), max_length=MAX_VARCHAR_CITY
    )
    if not city_clean:
        failures.append((RULE_CITY_MISSING, "city missing"))
    parsed["city_name"] = city_clean
    parsed["city_repaired"] = city_repaired

    rating_val, rating_valid = parse_rating(
        payload.get("Aggregate rating", ""),
        payload.get("Rating text", ""),
        min_rating=config.quality_rating_min,
        max_rating=config.quality_rating_max,
    )
    if not rating_valid:
        failures.append(
            (
                RULE_RATING_OUT_OF_RANGE,
                f"rating outside {config.quality_rating_min}"
                f"-{config.quality_rating_max}",
            )
        )
    parsed["rating"] = rating_val

    votes_val = _parse_votes(payload.get("Votes", ""))
    if votes_val is None:
        failures.append((RULE_VOTES_NEGATIVE, "votes negative or not an integer"))
    parsed["votes"] = votes_val

    cost_val, cost_status = parse_cost(payload.get("Average Cost for two", ""))
    if cost_status in {"negative", "invalid"}:
        failures.append(
            (RULE_COST_NEGATIVE, "average cost for two negative or non-numeric")
        )
    parsed["cost_val"] = cost_val
    parsed["cost_status"] = cost_status

    price_range_val = _parse_price_range(
        payload.get("Price range", ""),
        config.quality_price_range_min,
        config.quality_price_range_max,
    )
    if price_range_val is None:
        failures.append(
            (
                RULE_PRICE_RANGE_INVALID,
                f"price range outside {config.quality_price_range_min}"
                f"-{config.quality_price_range_max}",
            )
        )
    parsed["price_range"] = price_range_val

    table_booking = parse_boolean_flag(payload.get("Has Table booking", ""))
    online_delivery = parse_boolean_flag(payload.get("Has Online delivery", ""))
    delivering_now = parse_boolean_flag(payload.get("Is delivering now", ""))
    switch_menu = parse_boolean_flag(payload.get("Switch to order menu", ""))
    if (
        table_booking is None
        or online_delivery is None
        or delivering_now is None
        or switch_menu is None
    ):
        failures.append((RULE_BOOLEAN_FLAG_INVALID, "boolean flag not Yes or No"))
    parsed["has_table_booking"] = table_booking
    parsed["has_online_delivery"] = online_delivery
    parsed["is_delivering_now"] = delivering_now
    parsed["switch_to_order_menu"] = switch_menu

    return failures, parsed


def _build_standardized_with_warnings(
    payload: dict[str, str],
    parsed: dict[str, object],
    *,
    source_id: int,
    vocabulary: CuisineVocabulary,
    config: PipelineRuntimeConfig,
    fx_rates: Mapping[str, Decimal] | None,
    fx_rate_date: date | None,
) -> tuple[StandardizedRestaurant, list[tuple[str, str]]]:
    """Build a ``StandardizedRestaurant`` and collect all warning-level issues."""
    warnings: list[tuple[str, str]] = []

    source_restaurant_id = str(parsed["source_restaurant_id"])
    name_clean = str(parsed["name"])
    city_clean = str(parsed["city_name"])
    country_code = int(str(parsed["country_code"]))
    country_meta = COUNTRY_CODE_TO_METADATA[country_code]

    locality_clean, locality_repaired = repair_text(
        payload.get("Locality", ""), max_length=MAX_VARCHAR_LOCALITY
    )
    if not locality_clean:
        locality_clean = DEFAULT_LOCALITY_FALLBACK

    address_clean, address_repaired = repair_text(
        payload.get("Address", ""), max_length=MAX_VARCHAR_ADDRESS
    )
    rating_color_clean, color_repaired = repair_text(
        payload.get("Rating color", ""), max_length=MAX_VARCHAR_RATING_COLOR
    )
    rating_text_clean, rating_text_repaired = repair_text(
        payload.get("Rating text", ""), max_length=MAX_VARCHAR_RATING_TEXT
    )

    lat_val, lng_val, coord_status = parse_coordinates(
        payload.get("Latitude", ""),
        payload.get("Longitude", ""),
        max_abs_lat=config.quality_latitude_abs_max,
        max_abs_lng=config.quality_longitude_abs_max,
    )
    if coord_status == "missing":
        warnings.append(
            (RULE_COORDINATES_MISSING, "coordinates missing or zero; set to NULL")
        )
    elif coord_status == "out_of_range":
        warnings.append(
            (RULE_COORDINATES_OUT_OF_RANGE, "coordinates out of range; set to NULL")
        )

    cost_val = parsed["cost_val"]
    cost_status = str(parsed["cost_status"])
    if cost_status == "zero":
        warnings.append((RULE_COST_ZERO, "average cost for two is zero; set to NULL"))

    currency_res = resolve_country_currency(
        country_code=country_code,
        raw_currency_label=payload.get("Currency", ""),
        avg_cost_for_two=cost_val if isinstance(cost_val, Decimal) else None,
        fx_rates=fx_rates,
        fx_rate_date=fx_rate_date,
    )
    if currency_res.label_mismatched:
        warnings.append(
            (
                RULE_CURRENCY_LABEL_MISMATCH,
                "currency label disagrees with country; country currency used",
            )
        )

    cuisine_res = normalize_cuisines(payload.get("Cuisines", ""), vocabulary)
    if cuisine_res.is_missing:
        warnings.append((RULE_CUISINE_MISSING, "no cuisine listed"))
    if cuisine_res.unmapped_labels:
        joined = ", ".join(cuisine_res.unmapped_labels)
        warnings.append(
            (
                RULE_CUISINE_UNMAPPED,
                f"cuisine label not in vocabulary; kept as is: {joined}",
            )
        )

    any_mojibake_repaired = any(
        [
            bool(parsed["name_repaired"]),
            bool(parsed["city_repaired"]),
            locality_repaired,
            address_repaired,
            color_repaired,
            rating_text_repaired,
            currency_res.label_mojibake_repaired,
            cuisine_res.mojibake_repaired,
        ]
    )
    if any_mojibake_repaired:
        warnings.append((RULE_TEXT_MOJIBAKE_REPAIRED, "mis-encoded text repaired"))

    rating_val = parsed["rating"] if isinstance(parsed["rating"], Decimal) else None
    votes_val = int(str(parsed["votes"]))
    price_range_val = int(str(parsed["price_range"]))
    has_table_booking = bool(parsed["has_table_booking"])
    has_online_delivery = bool(parsed["has_online_delivery"])
    is_delivering_now = bool(parsed["is_delivering_now"])
    switch_to_order_menu = bool(parsed["switch_to_order_menu"])

    record_hash = compute_record_hash(
        source_id=source_id,
        source_restaurant_id=source_restaurant_id,
        name=name_clean,
        source_country_code=country_code,
        city_name=city_clean,
        locality=locality_clean,
        address=address_clean or None,
        latitude=lat_val,
        longitude=lng_val,
        avg_cost_for_two=currency_res.avg_cost_for_two,
        currency_code=currency_res.currency_code,
        avg_cost_for_two_usd=currency_res.avg_cost_for_two_usd,
        fx_rate=currency_res.fx_rate,
        fx_rate_date=currency_res.fx_rate_date,
        price_range=price_range_val,
        rating=rating_val,
        rating_color=rating_color_clean or None,
        rating_text=rating_text_clean or None,
        votes=votes_val,
        has_table_booking=has_table_booking,
        has_online_delivery=has_online_delivery,
        is_delivering_now=is_delivering_now,
        switch_to_order_menu=switch_to_order_menu,
        cuisines=cuisine_res.mappings,
    )

    standardized = StandardizedRestaurant(
        source_id=source_id,
        source_restaurant_id=source_restaurant_id,
        name=name_clean,
        source_country_code=country_code,
        country_name=country_meta["country_name"],
        iso_code=country_meta["iso_code"],
        city_name=city_clean,
        locality=locality_clean,
        address=address_clean or None,
        latitude=lat_val,
        longitude=lng_val,
        avg_cost_for_two=currency_res.avg_cost_for_two,
        currency_code=currency_res.currency_code,
        avg_cost_for_two_usd=currency_res.avg_cost_for_two_usd,
        fx_rate=currency_res.fx_rate,
        fx_rate_date=currency_res.fx_rate_date,
        price_range=price_range_val,
        rating=rating_val,
        rating_color=rating_color_clean or None,
        rating_text=rating_text_clean or None,
        votes=votes_val,
        has_table_booking=has_table_booking,
        has_online_delivery=has_online_delivery,
        is_delivering_now=is_delivering_now,
        switch_to_order_menu=switch_to_order_menu,
        cuisines=cuisine_res.mappings,
        record_hash=record_hash,
    )
    return standardized, warnings


def validate_and_standardize_batch(
    raw_df: pd.DataFrame,
    *,
    source_id: int,
    vocabulary: CuisineVocabulary,
    config: PipelineRuntimeConfig,
    fx_rates: Mapping[str, Decimal] | None = None,
    fx_rate_date: date | None = None,
) -> ValidationResult:
    """Validate all rows in ``raw_df`` and return Silver-ready objects and issues.

    Args:
        raw_df: Raw DataFrame loaded from the Zomato CSV.
        source_id: Numeric ``source_metadata.source_id`` value.
        vocabulary: Loaded ``CuisineVocabulary`` lookup.
        config: Non-secret pipeline runtime configuration.
        fx_rates: Optional batch-pinned FX map (``currency_code -> USD rate``).
        fx_rate_date: Optional batch-pinned FX effective date.

    Returns:
        ``ValidationResult`` separating valid records, rejected records, and
        all logged quality issues.
    """
    duplicate_ids = _find_duplicate_source_ids(raw_df)
    valid_records: list[StandardizedRestaurant] = []
    rejected_records: list[RejectedRecord] = []
    issues: list[QualityIssue] = []
    rows_warned = 0
    detected_at = datetime.now(UTC)

    for row_dict in raw_df.to_dict(orient="records"):
        payload = _to_raw_payload(row_dict)
        raw_id = payload.get("Restaurant ID", "").strip()
        source_record_id = raw_id[:MAX_VARCHAR_SOURCE_RECORD_ID] if raw_id else None

        reject_failures, parsed = _evaluate_reject_rules(payload, duplicate_ids, config)
        if reject_failures:
            primary_rule, primary_reason = reject_failures[0]
            rejected_records.append(
                RejectedRecord(
                    source_record_id=source_record_id,
                    rule_name=primary_rule,
                    reason=primary_reason[:MAX_VARCHAR_REASON],
                    raw_payload=payload,
                )
            )
            for rule_name, reason in reject_failures:
                issues.append(
                    QualityIssue(
                        source_record_id=source_record_id,
                        rule_name=rule_name,
                        severity=SEVERITY_REJECT,
                        reason=reason[:MAX_VARCHAR_REASON],
                        raw_payload=payload,
                        detected_at=detected_at,
                    )
                )
            continue

        standardized, warnings = _build_standardized_with_warnings(
            payload,
            parsed,
            source_id=source_id,
            vocabulary=vocabulary,
            config=config,
            fx_rates=fx_rates,
            fx_rate_date=fx_rate_date,
        )
        valid_records.append(standardized)

        if warnings:
            rows_warned += 1
            for rule_name, reason in warnings:
                issues.append(
                    QualityIssue(
                        source_record_id=standardized.source_restaurant_id,
                        rule_name=rule_name,
                        severity=SEVERITY_WARNING,
                        reason=reason[:MAX_VARCHAR_REASON],
                        raw_payload=payload,
                        detected_at=detected_at,
                    )
                )

    logger.info(
        "Validated batch: read=%d valid=%d rejected=%d warned=%d",
        len(raw_df),
        len(valid_records),
        len(rejected_records),
        rows_warned,
    )
    return ValidationResult(
        records_read=len(raw_df),
        valid_records=valid_records,
        rejected_records=rejected_records,
        issues=issues,
        rows_warned=rows_warned,
    )
