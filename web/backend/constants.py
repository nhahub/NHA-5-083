"""Domain constants, static reference lookups, and bounds for the FastAPI backend."""

from __future__ import annotations

from decimal import Decimal
from typing import TypedDict

NLP_TIMEOUT_SECONDS = 5
MAX_NLP_INPUT_CHARS = 500
MAX_NLP_OUTPUT_TOKENS = 256
QUERY_LOG_MAX_CHARS = 220
GOLD_MAX_AGE_DAYS = 7
DEFAULT_SEMANTIC_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_SEMANTIC_CUISINE_THRESHOLD = 0.48
DEFAULT_SEMANTIC_PRICE_THRESHOLD = 0.44
DEFAULT_SEMANTIC_PRICE_MARGIN = 0.04

METERS_PER_DEGREE_LATITUDE = 111_320.0
MAX_SEARCH_RADIUS_M = 50_000.0
MAX_ABS_LATITUDE = 85.0
MAX_ABS_LONGITUDE = 180.0
MAX_GEO_LATITUDE = 90.0
BOX_MARGIN = 1.01
EARTH_RADIUS_METERS = 6_371_000.0
WGS84_SRID = 4326

DEFAULT_PAGE_LIMIT = 20
MIN_PAGE_LIMIT = 1
MAX_PAGE_LIMIT = 100
DEFAULT_MAP_LIMIT = 500
MAX_MAP_LIMIT = 2000

MIN_RATING = 0.0
MAX_RATING = 5.0
MIN_PRICE_RANGE = 1
MAX_PRICE_RANGE = 4
MIN_COST = 0.0

DEFAULT_NEARBY_RADIUS_M = 5_000.0
NEARBY_LIMIT = 6
SIMILAR_LIMIT = 6
TOP_CITIES_LIMIT = 6
TOP_CUISINES_LIMIT = 10
TOP_DEST_CUISINES_LIMIT = 8
TOP_RESTAURANTS_LIMIT = 6
RECENT_RUNS_LIMIT = 20

RATE_LIMIT_WINDOW_SECONDS = 60
DEFAULT_NLP_RATE_LIMIT_PER_MINUTE = 30
DEFAULT_CACHE_MAX_ENTRIES = 1000
DEFAULT_CACHE_TTL_SECONDS = 3600
SECONDS_PER_DAY = 86_400.0

ZOMATO_SOURCE_ID = 1
ZOMATO_SOURCE_NAME = "zomato"
ZOMATO_SOURCE_LICENSE = "CC0 1.0"
DEFAULT_CSV_ENCODING = "latin-1"

PRICE_RANGE_TIER_ONE = 1
PRICE_RANGE_TIER_TWO = 2
PRICE_RANGE_TIER_THREE = 3
PRICE_RANGE_TIER_FOUR = 4

RATING_EXCELLENT_MIN = 4.5
RATING_VERY_GOOD_MIN = 4.0
RATING_GOOD_MIN = 3.5
RATING_AVERAGE_MIN = 2.5

SUCCESS_RUN_STATUSES: frozenset[str] = frozenset({"success", "skipped_unchanged"})
PLACEHOLDER_PREFIX = "replace_with_"
UNCONFIGURED_MODEL_MARKER = "replace_after_"


class CountryMetadata(TypedDict):
    """Static metadata for a Zomato country code."""

    country_name: str
    iso_code: str
    currency_code: str


class CultureProfile(TypedDict):
    """Curated editorial destination culture metadata."""

    tagline: str
    dining_tradition: str
    signature_dishes: list[str]
    attribution: str


COUNTRY_CODE_TO_METADATA: dict[int, CountryMetadata] = {
    1: {"country_name": "India", "iso_code": "IN", "currency_code": "INR"},
    14: {"country_name": "Australia", "iso_code": "AU", "currency_code": "AUD"},
    30: {"country_name": "Brazil", "iso_code": "BR", "currency_code": "BRL"},
    37: {"country_name": "Canada", "iso_code": "CA", "currency_code": "CAD"},
    94: {"country_name": "Indonesia", "iso_code": "ID", "currency_code": "IDR"},
    148: {"country_name": "New Zealand", "iso_code": "NZ", "currency_code": "NZD"},
    162: {"country_name": "Philippines", "iso_code": "PH", "currency_code": "PHP"},
    166: {"country_name": "Qatar", "iso_code": "QA", "currency_code": "QAR"},
    184: {"country_name": "Singapore", "iso_code": "SG", "currency_code": "SGD"},
    189: {"country_name": "South Africa", "iso_code": "ZA", "currency_code": "ZAR"},
    191: {"country_name": "Sri Lanka", "iso_code": "LK", "currency_code": "LKR"},
    208: {"country_name": "Turkey", "iso_code": "TR", "currency_code": "TRY"},
    214: {"country_name": "UAE", "iso_code": "AE", "currency_code": "AED"},
    215: {"country_name": "United Kingdom", "iso_code": "GB", "currency_code": "GBP"},
    216: {"country_name": "United States", "iso_code": "US", "currency_code": "USD"},
}

COUNTRY_ALIASES: dict[str, str] = {
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "us": "United States",
    "u.s.": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "united arab emirates": "UAE",
    "emirates": "UAE",
}

CITY_ALIASES: dict[str, str] = {
    "delhi": "New Delhi",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "bengaluru": "Bangalore",
    "madras": "Chennai",
    "gurugram": "Gurgaon",
}

DEFAULT_PINNED_FX_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1.000000"),
    "INR": Decimal("0.012000"),
    "AUD": Decimal("0.650000"),
    "BRL": Decimal("0.175000"),
    "CAD": Decimal("0.720000"),
    "IDR": Decimal("0.000063"),
    "NZD": Decimal("0.590000"),
    "PHP": Decimal("0.017000"),
    "QAR": Decimal("0.274725"),
    "SGD": Decimal("0.745000"),
    "ZAR": Decimal("0.055000"),
    "LKR": Decimal("0.003400"),
    "TRY": Decimal("0.029000"),
    "AED": Decimal("0.272294"),
    "GBP": Decimal("1.270000"),
}

MOJIBAKE_REPLACEMENTS: dict[str, str] = {
    "Dï¿½_ner": "Döner",
    "Bï¿½_rek": "Börek",
    "Brasï¿½_lia": "Brasília",
    "Sï¿½ï¿½o Paulo": "São Paulo",
    "ï¿½ï¿½stanbul": "İstanbul",
}

DESTINATION_CULTURE: dict[str, CultureProfile] = {
    "India": {
        "tagline": (
            "A subcontinent of regional spice traditions, tandoor craft, "
            "and royal Mughlai kitchens."
        ),
        "dining_tradition": (
            "Deeply regional menus spanning North Indian tandoors, South Indian "
            "fermented batters, and vibrant street-food bazaars."
        ),
        "signature_dishes": [
            "Biryani",
            "Butter Chicken",
            "Masala Dosa",
            "Chaat",
            "Rogan Josh",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "UAE": {
        "tagline": (
            "Cosmopolitan fine dining meets Emirati hospitality and "
            "Levantine spice routes."
        ),
        "dining_tradition": (
            "A global crossroads blending traditional Arabian hospitality with "
            "international chef-led dining districts."
        ),
        "signature_dishes": [
            "Machboos",
            "Shawarma",
            "Luqaimat",
            "Grilled Kebabs",
            "Levantine Mezze",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "United Kingdom": {
        "tagline": (
            "Historic gastropubs, world-class curry houses, and "
            "multicultural market kitchens."
        ),
        "dining_tradition": (
            "Neighborhood pubs and historic food markets paired with one of "
            "the world's most diverse international dining scenes."
        ),
        "signature_dishes": [
            "Sunday Roast",
            "Fish & Chips",
            "British-Indian Curry",
            "Artisan Pies",
            "Afternoon Tea",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "United States": {
        "tagline": (
            "Regional smokehouses, classic diners, and coastal "
            "farm-to-table innovation."
        ),
        "dining_tradition": (
            "Distinct state-by-state culinary identities shaped by immigrant "
            "traditions, barbecue pits, and casual neighborhood grills."
        ),
        "signature_dishes": [
            "Regional BBQ",
            "Craft Burgers",
            "Cajun Gumbo",
            "New York Pizza",
            "Seafood Boils",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "Brazil": {
        "tagline": (
            "Flame-grilled churrasco, tropical coastal flavors, and "
            "lively neighborhood botecos."
        ),
        "dining_tradition": (
            "Social, unhurried meals built around charcoal-grilled meats, "
            "cassava, fresh seafood, and neighborhood bakeries."
        ),
        "signature_dishes": [
            "Feijoada",
            "Churrasco",
            "Pão de Queijo",
            "Moqueca",
            "Açaí",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "Turkey": {
        "tagline": (
            "Anatolian hearth cooking, Aegean olive-oil mezes, and "
            "centuries-old bazaar sweets."
        ),
        "dining_tradition": (
            "Generous multi-course tables starting with cold mezes and "
            "concluding with Turkish tea or coffee."
        ),
        "signature_dishes": [
            "Adana Kebab",
            "Meze Platters",
            "Pide",
            "Lahmacun",
            "Baklava",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "Singapore": {
        "tagline": (
            "UNESCO-recognized hawker heritage alongside precision "
            "modern Asian gastronomy."
        ),
        "dining_tradition": (
            "A fusion of Chinese, Malay, Indian, and Peranakan traditions "
            "celebrated in bustling hawker centers and fine dining rooms."
        ),
        "signature_dishes": [
            "Hainanese Chicken Rice",
            "Laksa",
            "Chilli Crab",
            "Char Kway Teow",
            "Satay",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "Philippines": {
        "tagline": (
            "Savory-tangy adobo, wood-fired lechon, and warm island hospitality."
        ),
        "dining_tradition": (
            "Family-style feasts balancing vinegar, garlic, soy, and tropical "
            "citrus across coastal and urban kitchens."
        ),
        "signature_dishes": ["Adobo", "Sinigang", "Lechon", "Sisig", "Halo-Halo"],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "Australia": {
        "tagline": (
            "Coastal produce, specialty coffee culture, and Pacific-rim creativity."
        ),
        "dining_tradition": (
            "Relaxed all-day brunch culture paired with modern Australian "
            "kitchens drawing on Mediterranean and Asian flavors."
        ),
        "signature_dishes": [
            "Barramundi",
            "Meat Pie",
            "Flat White Brunch",
            "Pavlova",
            "Sourdough Toasties",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
    "South Africa": {
        "tagline": (
            "Wood-fired braai traditions, Cape Malay spices, and vineyard dining."
        ),
        "dining_tradition": (
            "Vibrant open-fire gatherings and coastal kitchens blending "
            "indigenous ingredients with Dutch, Malay, and Indian influences."
        ),
        "signature_dishes": [
            "Bobotie",
            "Biltong",
            "Bunny Chow",
            "Boerewors",
            "Malva Pudding",
        ],
        "attribution": "Curated culinary reference (EatoSphere Editorial Metadata)",
    },
}

DEFAULT_DESTINATION_CULTURE: CultureProfile = {
    "tagline": (
        "Local culinary traditions and international dining experiences "
        "represented in the dataset."
    ),
    "dining_tradition": (
        "Explore represented cuisines, top-rated neighborhoods, and local "
        "dining spots directly from verified dataset records."
    ),
    "signature_dishes": [
        "Regional Specialties",
        "Local Cafes",
        "International Dining",
    ],
    "attribution": "Derived from dataset coverage (EatoSphere)",
}
