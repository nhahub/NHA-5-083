"""Named constants, quality rule identifiers, bounds, and lookup tables."""

from datetime import date
from decimal import Decimal
from typing import TypedDict

# ---------------------------------------------------------------------------
# Batch-level data quality rule names (docs/DATA_QUALITY_RULES.md)
# ---------------------------------------------------------------------------
RULE_SCHEMA_COLUMNS_MISSING = "schema_columns_missing"
RULE_FILE_DECODE_FAILED = "file_decode_failed"
RULE_BATCH_EMPTY = "batch_empty"

# ---------------------------------------------------------------------------
# Record-level reject rule names
# ---------------------------------------------------------------------------
RULE_SOURCE_ID_MISSING = "source_id_missing"
RULE_SOURCE_ID_DUPLICATE_IN_BATCH = "source_id_duplicate_in_batch"
RULE_NAME_MISSING = "name_missing"
RULE_COUNTRY_CODE_UNKNOWN = "country_code_unknown"
RULE_CITY_MISSING = "city_missing"
RULE_RATING_OUT_OF_RANGE = "rating_out_of_range"
RULE_VOTES_NEGATIVE = "votes_negative"
RULE_COST_NEGATIVE = "cost_negative"
RULE_PRICE_RANGE_INVALID = "price_range_invalid"
RULE_BOOLEAN_FLAG_INVALID = "boolean_flag_invalid"

# ---------------------------------------------------------------------------
# Record-level warning rule names
# ---------------------------------------------------------------------------
RULE_COORDINATES_MISSING = "coordinates_missing"
RULE_COORDINATES_OUT_OF_RANGE = "coordinates_out_of_range"
RULE_COST_ZERO = "cost_zero"
RULE_CUISINE_MISSING = "cuisine_missing"
RULE_CUISINE_UNMAPPED = "cuisine_unmapped"
RULE_CURRENCY_LABEL_MISMATCH = "currency_label_mismatch"
RULE_TEXT_MOJIBAKE_REPAIRED = "text_mojibake_repaired"

# ---------------------------------------------------------------------------
# Issue severities and pipeline run statuses
# ---------------------------------------------------------------------------
SEVERITY_REJECT = "reject"
SEVERITY_WARNING = "warning"

RUN_STATUS_RUNNING = "running"
RUN_STATUS_SUCCESS = "success"
RUN_STATUS_SKIPPED_UNCHANGED = "skipped_unchanged"
RUN_STATUS_QUALITY_GATE_FAILED = "quality_gate_failed"
RUN_STATUS_FAILED = "failed"

# ---------------------------------------------------------------------------
# Quality gate and domain bounds
# ---------------------------------------------------------------------------
MAX_QUARANTINE_RATE = 0.15
MIN_RATING = 0.0
MAX_RATING = 5.0
MIN_PRICE_RANGE = 1
MAX_PRICE_RANGE = 4
MAX_ABS_LATITUDE = 90.0
MAX_ABS_LONGITUDE = 180.0
MAX_MAP_LATITUDE = 85.0
MIN_VOTES = 0
MIN_COST = Decimal("0")

QUERY_LOG_MAX_CHARS = 220
GOLD_MAX_AGE_DAYS = 7
QUARANTINE_RATE_DECIMALS = 4

# ---------------------------------------------------------------------------
# Precision & truncation limits matching sql/001_create_tables.sql
# ---------------------------------------------------------------------------
DECIMAL_MONEY_QUANT = Decimal("0.01")
DECIMAL_FX_QUANT = Decimal("0.000001")
DECIMAL_COORD_QUANT = Decimal("0.000001")
DECIMAL_RATING_QUANT = Decimal("0.1")

MAX_VARCHAR_SOURCE_RECORD_ID = 64
MAX_VARCHAR_NAME = 255
MAX_VARCHAR_ADDRESS = 500
MAX_VARCHAR_CITY = 100
MAX_VARCHAR_LOCALITY = 150
MAX_VARCHAR_RATING_COLOR = 32
MAX_VARCHAR_RATING_TEXT = 32
MAX_VARCHAR_REASON = 500
MAX_VARCHAR_CUISINES_LIST = 500

RATING_NOT_RATED_TEXT = "not rated"
DEFAULT_LOCALITY_FALLBACK = "Unknown"
BOOLEAN_TRUE_LABEL = "Yes"
BOOLEAN_FALSE_LABEL = "No"
SHA256_HEX_LENGTH = 64
COORD_ZERO = 0.0

# ---------------------------------------------------------------------------
# Source & Airflow defaults
# ---------------------------------------------------------------------------
DEFAULT_ZOMATO_SOURCE_ID = 1
DEFAULT_ZOMATO_SOURCE_NAME = "zomato"
DEFAULT_ZOMATO_DAG_ID = "zomato_weekly_etl"
DEFAULT_ZOMATO_LICENSE = "CC0 1.0"
DEFAULT_ZOMATO_URL = (
    "https://www.kaggle.com/datasets/shrutimehta/zomato-restaurants-data"
)
MYSQL_PIPELINE_CONN_ID = "mysql_pipeline"
AZURE_BLOB_BRONZE_CONN_ID = "azure_blob_bronze"

STORAGE_BACKEND_LOCAL = "local"
STORAGE_BACKEND_AZURE = "azure"

DEFAULT_RETRY_COUNT = 2
DEFAULT_RETRY_DELAY_MINUTES = 5
DEFAULT_EXECUTION_TIMEOUT_MINUTES = 30
DEFAULT_SQL_BATCH_SIZE = 500

# ---------------------------------------------------------------------------
# Zomato schema columns (exact 21 columns)
# ---------------------------------------------------------------------------
ZOMATO_EXPECTED_COLUMNS: tuple[str, ...] = (
    "Restaurant ID",
    "Restaurant Name",
    "Country Code",
    "City",
    "Address",
    "Locality",
    "Locality Verbose",
    "Longitude",
    "Latitude",
    "Cuisines",
    "Average Cost for two",
    "Currency",
    "Has Table booking",
    "Has Online delivery",
    "Is delivering now",
    "Switch to order menu",
    "Price range",
    "Aggregate rating",
    "Rating color",
    "Rating text",
    "Votes",
)


class CountryMetadata(TypedDict):
    """Metadata describing a Zomato source country code."""

    country_name: str
    iso_code: str
    currency_code: str
    accepted_zomato_currencies: tuple[str, ...]


COUNTRY_CODE_TO_METADATA: dict[int, CountryMetadata] = {
    1: {
        "country_name": "India",
        "iso_code": "IN",
        "currency_code": "INR",
        "accepted_zomato_currencies": ("Indian Rupees(Rs.)", "INR"),
    },
    14: {
        "country_name": "Australia",
        "iso_code": "AU",
        "currency_code": "AUD",
        "accepted_zomato_currencies": ("Dollar($)", "AUD"),
    },
    30: {
        "country_name": "Brazil",
        "iso_code": "BR",
        "currency_code": "BRL",
        "accepted_zomato_currencies": ("Brazilian Real(R$)", "BRL"),
    },
    37: {
        "country_name": "Canada",
        "iso_code": "CA",
        "currency_code": "CAD",
        "accepted_zomato_currencies": ("Dollar($)", "CAD"),
    },
    94: {
        "country_name": "Indonesia",
        "iso_code": "ID",
        "currency_code": "IDR",
        "accepted_zomato_currencies": ("Indonesian Rupiah(IDR)", "IDR"),
    },
    148: {
        "country_name": "New Zealand",
        "iso_code": "NZ",
        "currency_code": "NZD",
        "accepted_zomato_currencies": ("NewZealand($)", "NZD"),
    },
    162: {
        "country_name": "Philippines",
        "iso_code": "PH",
        "currency_code": "PHP",
        "accepted_zomato_currencies": ("Philippine Peso(PHP)", "PHP"),
    },
    166: {
        "country_name": "Qatar",
        "iso_code": "QA",
        "currency_code": "QAR",
        "accepted_zomato_currencies": ("Qatari Rial(QR)", "QAR"),
    },
    184: {
        "country_name": "Singapore",
        "iso_code": "SG",
        "currency_code": "SGD",
        "accepted_zomato_currencies": ("Dollar($)", "SGD"),
    },
    189: {
        "country_name": "South Africa",
        "iso_code": "ZA",
        "currency_code": "ZAR",
        "accepted_zomato_currencies": ("Rand(R)", "ZAR"),
    },
    191: {
        "country_name": "Sri Lanka",
        "iso_code": "LK",
        "currency_code": "LKR",
        "accepted_zomato_currencies": ("Sri Lankan Rupee(LKR)", "LKR"),
    },
    208: {
        "country_name": "Turkey",
        "iso_code": "TR",
        "currency_code": "TRY",
        "accepted_zomato_currencies": ("Turkish Lira(TL)", "TRY"),
    },
    214: {
        "country_name": "UAE",
        "iso_code": "AE",
        "currency_code": "AED",
        "accepted_zomato_currencies": (
            "Emirati Diram(AED)",
            "Emirati Dirham(AED)",
            "AED",
        ),
    },
    215: {
        "country_name": "United Kingdom",
        "iso_code": "GB",
        "currency_code": "GBP",
        "accepted_zomato_currencies": ("Pounds(£)", "GBP"),
    },
    216: {
        "country_name": "United States",
        "iso_code": "US",
        "currency_code": "USD",
        "accepted_zomato_currencies": ("Dollar($)", "USD"),
    },
}

# Ordered longest-first or exact phrase matches before shorter fragments
# so specific sequences like Pounds(ï¿½ï¿½) and Cafï¿½ï¿½ repair accurately.
KNOWN_MOJIBAKE_MAP: dict[str, str] = {
    "Pounds(ï¿½ï¿½)": "Pounds(£)",
    "Dï¿½_ner": "Döner",
    "Bï¿½_rek": "Börek",
    "Cafï¿½ï¿½": "Café",
    "Sï¿½ï¿½o Paulo": "São Paulo",
    "Brasï¿½_lia": "Brasília",
    "ï¿½guas Claras": "Águas Claras",
    "Joï¿½ï¿½o": "João",
    "Aprazï¿½_vel": "Aprazível",
    "Gï¿½ï¿½vea": "Gávea",
    "Bon Appï¿½ï¿½tit": "Bon Appétit",
    "Araucï¿½ï¿½rias": "Araucárias",
    "Eskiï¿½ï¿½ehir": "Eskişehir",
    "Beï¿½ï¿½iktaï¿½ï¿½": "Beşiktaş",
    "ï¿½ï¿½stanbul": "İstanbul",
    "ï¿½ankaya": "Çankaya",
    "KadÛ±kï¿½_y": "Kadıköy",
    "AsmalÛ±mescit": "Asmalimescit",
    "OsmanlÛ±": "Osmanlı",
    "ï¿½ï¿½stiklal": "İstiklal",
    "Cevdetpaï¿½ï¿½a": "Cevdetpaşa",
    "Beyoï¿½ï¿½lu": "Beyoğlu",
    "Baï¿½ï¿½dat": "Bağdat",
    "Cafeaï¿½ï¿½a": "Caferağa",
    "Caferaï¿½ï¿½a": "Caferağa",
    "BademaltÛ±": "Bademaltı",
    "Neï¿½ï¿½et": "Neşet",
    "ï¿½_mer": "Ömer",
    "Aï¿½ï¿½ï¿½k": "Açık",
    "Sï¿½_ï¿½ï¿½ï¿½_tï¿½_zï¿½_": "Söğütözü",
}

DEFAULT_PINNED_FX_DATE = date(2026, 11, 24)

DEFAULT_PINNED_FX_RATES_TO_USD: dict[str, Decimal] = {
    "AED": Decimal("0.272294"),
    "AUD": Decimal("0.650000"),
    "BRL": Decimal("0.172000"),
    "CAD": Decimal("0.715000"),
    "GBP": Decimal("1.260000"),
    "IDR": Decimal("0.000063"),
    "INR": Decimal("0.011900"),
    "LKR": Decimal("0.003400"),
    "NZD": Decimal("0.590000"),
    "PHP": Decimal("0.017000"),
    "QAR": Decimal("0.274725"),
    "SGD": Decimal("0.745000"),
    "TRY": Decimal("0.029000"),
    "USD": Decimal("1.000000"),
    "ZAR": Decimal("0.055000"),
}
