"""Tests for cuisine normalization, mojibake repair, ratings, and FX USD conversion."""

from datetime import date
from decimal import Decimal

import pandas as pd

from pipeline.constants import ZOMATO_EXPECTED_COLUMNS
from pipeline.quality.validator import validate_and_standardize_batch
from pipeline.settings import PipelineRuntimeConfig
from pipeline.transform.cuisines import CuisineVocabulary, normalize_cuisines
from pipeline.transform.currency import resolve_country_currency
from pipeline.transform.standardize import parse_rating, repair_text


def test_cuisine_map_loads_and_merges_and_deduplicates() -> None:
    vocab = CuisineVocabulary.from_csv()
    assert len(vocab) >= 145

    result = normalize_cuisines("Dï¿½_ner, Bï¿½_rek, Tea, Coffee and Tea", vocab)
    assert result.mojibake_repaired is True
    assert result.is_missing is False
    assert result.unmapped_labels == ()
    assert result.canonical_names == ("Turkish", "Coffee & Tea")
    assert result.cuisine_groups == (
        "Middle Eastern and Turkish",
        "Cafe and Beverages",
    )


def test_cuisine_unmapped_is_kept_as_is() -> None:
    vocab = CuisineVocabulary.from_csv()
    result = normalize_cuisines("North Indian, Imaginary Space Food", vocab)
    assert result.canonical_names == ("North Indian", "Imaginary Space Food")
    assert result.unmapped_labels == ("Imaginary Space Food",)


def test_mojibake_text_repairs() -> None:
    cleaned_gbp, rep_gbp = repair_text("Pounds(ï¿½ï¿½)")
    assert cleaned_gbp == "Pounds(£)"
    assert rep_gbp is True

    cleaned_city, rep_city = repair_text("Sï¿½ï¿½o Paulo")
    assert cleaned_city == "São Paulo"
    assert rep_city is True

    cleaned_cafe, rep_cafe = repair_text("4 Barrels Cafï¿½ï¿½ & Lounge")
    assert cleaned_cafe == "4 Barrels Café & Lounge"
    assert rep_cafe is True


def test_unrated_zero_becomes_none() -> None:
    rating, is_valid = parse_rating("0", "Not rated", min_rating=0.0, max_rating=5.0)
    assert is_valid is True
    assert rating is None

    rated, is_valid_rated = parse_rating(
        "4.3", "Very Good", min_rating=0.0, max_rating=5.0
    )
    assert is_valid_rated is True
    assert rated == Decimal("4.3")


def test_currency_uses_country_lookup_and_decimal_fx() -> None:
    # UK with repaired Pounds(£) agrees with GBP
    uk = resolve_country_currency(
        215,
        "Pounds(ï¿½ï¿½)",
        Decimal("40"),
        fx_rates={"GBP": Decimal("1.250000")},
        fx_rate_date=date(2026, 11, 24),
    )
    assert uk.currency_code == "GBP"
    assert uk.label_mismatched is False
    assert uk.label_mojibake_repaired is True
    assert uk.avg_cost_for_two == Decimal("40.00")
    assert uk.avg_cost_for_two_usd == Decimal("50.00")

    # Philippines (162) with mislabeled "Botswana Pula(P)" uses PHP + mismatch warning
    ph = resolve_country_currency(
        162,
        "Botswana Pula(P)",
        Decimal("1000"),
        fx_rates={"PHP": Decimal("0.017000")},
        fx_rate_date=date(2026, 11, 24),
    )
    assert ph.currency_code == "PHP"
    assert ph.label_mismatched is True
    assert ph.avg_cost_for_two_usd == Decimal("17.00")


def test_record_hash_deterministic_and_changes_on_business_edit() -> None:
    vocab = CuisineVocabulary.from_csv()
    config = PipelineRuntimeConfig()
    row_a = {
        "Restaurant ID": "555",
        "Restaurant Name": "Dï¿½_ner House",
        "Country Code": "208",
        "City": "ï¿½ï¿½stanbul",
        "Address": "Test St",
        "Locality": "Beï¿½ï¿½iktaï¿½ï¿½",
        "Locality Verbose": "Beï¿½ï¿½iktaï¿½ï¿½, ï¿½ï¿½stanbul",
        "Longitude": "29.000000",
        "Latitude": "41.040000",
        "Cuisines": "Dï¿½_ner, Kebab",
        "Average Cost for two": "200",
        "Currency": "Turkish Lira(TL)",
        "Has Table booking": "No",
        "Has Online delivery": "No",
        "Is delivering now": "No",
        "Switch to order menu": "No",
        "Price range": "2",
        "Aggregate rating": "0",
        "Rating color": "White",
        "Rating text": "Not rated",
        "Votes": "0",
    }
    row_b = dict(row_a)
    row_b["Votes"] = "12"

    df_a = pd.DataFrame([row_a], columns=list(ZOMATO_EXPECTED_COLUMNS), dtype=str)
    df_b = pd.DataFrame([row_b], columns=list(ZOMATO_EXPECTED_COLUMNS), dtype=str)

    res_a1 = validate_and_standardize_batch(
        df_a, source_id=1, vocabulary=vocab, config=config
    )
    res_a2 = validate_and_standardize_batch(
        df_a, source_id=1, vocabulary=vocab, config=config
    )
    res_b = validate_and_standardize_batch(
        df_b, source_id=1, vocabulary=vocab, config=config
    )

    rec_a1 = res_a1.valid_records[0]
    rec_a2 = res_a2.valid_records[0]
    rec_b = res_b.valid_records[0]

    assert rec_a1.name == "Döner House"
    assert rec_a1.city_name == "İstanbul"
    assert rec_a1.rating is None
    assert rec_a1.record_hash == rec_a2.record_hash
    assert rec_a1.record_hash != rec_b.record_hash
