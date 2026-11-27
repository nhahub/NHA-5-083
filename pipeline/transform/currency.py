"""Currency resolution and Decimal USD conversion using country metadata."""

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from pipeline.constants import (
    COUNTRY_CODE_TO_METADATA,
    DECIMAL_FX_QUANT,
    DECIMAL_MONEY_QUANT,
    DEFAULT_PINNED_FX_DATE,
    DEFAULT_PINNED_FX_RATES_TO_USD,
    KNOWN_MOJIBAKE_MAP,
)


@dataclass(frozen=True)
class CurrencyConversionResult:
    """Result of deriving ISO 4217 currency and computing USD equivalent."""

    currency_code: str
    avg_cost_for_two: Decimal | None
    avg_cost_for_two_usd: Decimal | None
    fx_rate: Decimal
    fx_rate_date: date
    label_mismatched: bool
    repaired_label: str
    label_mojibake_repaired: bool


def _repair_currency_label(raw_label: str) -> tuple[str, bool]:
    repaired = raw_label
    changed = False
    for broken, fixed in KNOWN_MOJIBAKE_MAP.items():
        if broken in repaired:
            repaired = repaired.replace(broken, fixed)
            changed = True
    return unicodedata.normalize("NFC", repaired).strip(), changed


def resolve_country_currency(
    country_code: int,
    raw_currency_label: str | None,
    avg_cost_for_two: Decimal | None,
    *,
    fx_rates: Mapping[str, Decimal] | None = None,
    fx_rate_date: date | None = None,
) -> CurrencyConversionResult:
    """Derive ISO 4217 currency from ``country_code`` and convert cost to USD.

    Free-text ``Currency`` labels are never trusted alone (for example, Zomato
    uses ``Dollar($)`` across multiple countries and ``Botswana Pula(P)`` for
    the Philippines). When the repaired label disagrees with the country's
    accepted labels, ``label_mismatched`` is ``True`` so the caller logs a
    ``currency_label_mismatch`` warning while still applying the country's
    authoritative ISO 4217 code.

    Args:
        country_code: Validated Zomato numeric country code.
        raw_currency_label: Raw ``Currency`` column text from the source row.
        avg_cost_for_two: Validated cost in local currency, or ``None``.
        fx_rates: Optional batch-pinned FX map (``currency_code -> USD rate``).
        fx_rate_date: Optional batch-pinned FX effective date.

    Returns:
        ``CurrencyConversionResult`` with exact ``Decimal`` amounts and rate.

    Raises:
        KeyError: If ``country_code`` is not in ``COUNTRY_CODE_TO_METADATA`` or
            the currency code has no configured FX rate.
    """
    metadata = COUNTRY_CODE_TO_METADATA[country_code]
    currency_code = metadata["currency_code"]
    accepted_labels = metadata["accepted_zomato_currencies"]

    repaired_label, mojibake_repaired = _repair_currency_label(raw_currency_label or "")
    label_mismatched = repaired_label not in accepted_labels

    rates_table = fx_rates if fx_rates is not None else DEFAULT_PINNED_FX_RATES_TO_USD
    if currency_code not in rates_table:
        raise KeyError(f"Missing FX rate for currency code {currency_code!r}")

    rate = rates_table[currency_code].quantize(DECIMAL_FX_QUANT, rounding=ROUND_HALF_UP)
    effective_date = (
        fx_rate_date if fx_rate_date is not None else DEFAULT_PINNED_FX_DATE
    )

    quantized_local: Decimal | None = None
    quantized_usd: Decimal | None = None
    if avg_cost_for_two is not None:
        quantized_local = avg_cost_for_two.quantize(
            DECIMAL_MONEY_QUANT, rounding=ROUND_HALF_UP
        )
        quantized_usd = (quantized_local * rate).quantize(
            DECIMAL_MONEY_QUANT, rounding=ROUND_HALF_UP
        )

    return CurrencyConversionResult(
        currency_code=currency_code,
        avg_cost_for_two=quantized_local,
        avg_cost_for_two_usd=quantized_usd,
        fx_rate=rate,
        fx_rate_date=effective_date,
        label_mismatched=label_mismatched,
        repaired_label=repaired_label,
        label_mojibake_repaired=mojibake_repaired,
    )
