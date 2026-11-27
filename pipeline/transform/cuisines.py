"""Cuisine vocabulary loading, mojibake repair, and canonical mapping."""

import csv
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from pipeline.constants import KNOWN_MOJIBAKE_MAP
from pipeline.settings import DEFAULT_CUISINE_MAP_PATH

UNMAPPED_CUISINE_GROUP = "Unmapped"


@dataclass(frozen=True)
class CuisineMapping:
    """Single canonical cuisine entry `(cuisine_name, cuisine_group)`."""

    cuisine_name: str
    cuisine_group: str


@dataclass(frozen=True)
class CuisineNormalizationResult:
    """Outcome of normalizing a raw comma-separated cuisines string."""

    mappings: tuple[CuisineMapping, ...]
    canonical_names: tuple[str, ...]
    cuisine_groups: tuple[str, ...]
    unmapped_labels: tuple[str, ...]
    mojibake_repaired: bool
    is_missing: bool


class CuisineVocabulary:
    """In-memory lookup table loaded from ``config/cuisine_map.csv``."""

    def __init__(self, entries: dict[str, CuisineMapping]) -> None:
        """Initialize the vocabulary with a source-label mapping.

        Args:
            entries: Mapping from trimmed source label to ``CuisineMapping``.
        """
        self._entries = dict(entries)

    @classmethod
    def from_csv(cls, csv_path: Path | None = None) -> "CuisineVocabulary":
        """Load the canonical cuisine vocabulary from a CSV file.

        Args:
            csv_path: Path to ``cuisine_map.csv``. Defaults to the repository
                ``config/cuisine_map.csv``.

        Returns:
            Initialized ``CuisineVocabulary`` instance.

        Raises:
            FileNotFoundError: If ``csv_path`` does not exist.
            ValueError: If required columns are missing from the CSV.
        """
        target = csv_path if csv_path is not None else DEFAULT_CUISINE_MAP_PATH
        if not target.is_file():
            raise FileNotFoundError(f"Cuisine map CSV not found: {target}")

        entries: dict[str, CuisineMapping] = {}
        with target.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            required = {"source_label", "canonical_cuisine", "cuisine_group"}
            fieldnames = set(reader.fieldnames or ())
            if not required.issubset(fieldnames):
                missing = sorted(required - fieldnames)
                raise ValueError(f"cuisine_map.csv missing columns: {missing}")

            for row in reader:
                source_label = unicodedata.normalize(
                    "NFC", (row["source_label"] or "").strip()
                )
                canonical = unicodedata.normalize(
                    "NFC", (row["canonical_cuisine"] or "").strip()
                )
                group = unicodedata.normalize(
                    "NFC", (row["cuisine_group"] or "").strip()
                )
                if source_label and canonical and group:
                    entries[source_label] = CuisineMapping(
                        cuisine_name=canonical,
                        cuisine_group=group,
                    )
        return cls(entries)

    def lookup(self, label: str) -> CuisineMapping | None:
        """Look up a single trimmed, repaired cuisine label.

        Args:
            label: Normalized source cuisine label.

        Returns:
            Matching ``CuisineMapping`` if known, else ``None``.
        """
        return self._entries.get(label)

    def __len__(self) -> int:
        """Return number of source labels in the vocabulary."""
        return len(self._entries)


def _repair_cuisine_label(raw_label: str) -> tuple[str, bool]:
    repaired = raw_label
    changed = False
    for broken, fixed in KNOWN_MOJIBAKE_MAP.items():
        if broken in repaired:
            repaired = repaired.replace(broken, fixed)
            changed = True
    normalized = unicodedata.normalize("NFC", repaired).strip()
    return normalized, changed


def normalize_cuisines(
    raw_cuisines: str | None,
    vocabulary: CuisineVocabulary,
) -> CuisineNormalizationResult:
    """Split, repair, map, and deduplicate a restaurant's cuisines list.

    Unmapped labels are preserved as-is with group ``Unmapped`` and returned
    in ``unmapped_labels`` so the caller can log a ``cuisine_unmapped`` warning.

    Args:
        raw_cuisines: Raw comma-separated cuisines string from the source.
        vocabulary: Loaded ``CuisineVocabulary`` lookup.

    Returns:
        ``CuisineNormalizationResult`` with canonical names, groups, and warnings.
    """
    if raw_cuisines is None or not raw_cuisines.strip():
        return CuisineNormalizationResult(
            mappings=(),
            canonical_names=(),
            cuisine_groups=(),
            unmapped_labels=(),
            mojibake_repaired=False,
            is_missing=True,
        )

    raw_items = [item.strip() for item in raw_cuisines.split(",") if item.strip()]
    if not raw_items:
        return CuisineNormalizationResult(
            mappings=(),
            canonical_names=(),
            cuisine_groups=(),
            unmapped_labels=(),
            mojibake_repaired=False,
            is_missing=True,
        )

    seen_canonical: set[str] = set()
    seen_groups: set[str] = set()
    mappings: list[CuisineMapping] = []
    canonical_names: list[str] = []
    cuisine_groups: list[str] = []
    unmapped_labels: list[str] = []
    mojibake_repaired = False

    for item in raw_items:
        cleaned_label, was_repaired = _repair_cuisine_label(item)
        if was_repaired:
            mojibake_repaired = True
        if not cleaned_label:
            continue

        matched = vocabulary.lookup(cleaned_label)
        if matched is None:
            if cleaned_label not in unmapped_labels:
                unmapped_labels.append(cleaned_label)
            mapping = CuisineMapping(
                cuisine_name=cleaned_label,
                cuisine_group=UNMAPPED_CUISINE_GROUP,
            )
        else:
            mapping = matched

        if mapping.cuisine_name not in seen_canonical:
            seen_canonical.add(mapping.cuisine_name)
            mappings.append(mapping)
            canonical_names.append(mapping.cuisine_name)

        if mapping.cuisine_group not in seen_groups:
            seen_groups.add(mapping.cuisine_group)
            cuisine_groups.append(mapping.cuisine_group)

    return CuisineNormalizationResult(
        mappings=tuple(mappings),
        canonical_names=tuple(canonical_names),
        cuisine_groups=tuple(cuisine_groups),
        unmapped_labels=tuple(unmapped_labels),
        mojibake_repaired=mojibake_repaired,
        is_missing=len(mappings) == 0,
    )
