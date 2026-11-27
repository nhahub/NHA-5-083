"""Programmatic Kaggle dataset metadata check, download, and checksum verification."""

import hashlib
import logging
import shutil
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from pipeline.constants import RUN_STATUS_SKIPPED_UNCHANGED

logger = logging.getLogger(__name__)

_HASH_CHUNK_BYTES = 65536


@dataclass(frozen=True)
class SourceMetadataSnapshot:
    """Version and timestamp metadata read from the upstream source."""

    source_name: str
    dataset_slug: str
    source_version: str | None
    source_updated_at: datetime | None
    title: str | None = None
    license_name: str | None = None


@dataclass(frozen=True)
class FetchResult:
    """Outcome of a check-before-download source fetch operation."""

    status: str
    snapshot: SourceMetadataSnapshot
    local_file_path: Path | None
    file_checksum: str | None


class KaggleClientProtocol(Protocol):
    """Minimal interface required from a Kaggle API client."""

    def get_dataset_metadata(self, dataset_slug: str) -> SourceMetadataSnapshot:
        """Fetch dataset version and update timestamp without downloading files."""

    def download_dataset(self, dataset_slug: str, destination_dir: Path) -> Path:
        """Download dataset files into ``destination_dir`` and return the directory."""


class DefaultKaggleClient:
    """Kaggle SDK client adapter using configured API credentials."""

    def get_dataset_metadata(self, dataset_slug: str) -> SourceMetadataSnapshot:
        """Fetch dataset metadata via the official Kaggle API.

        Args:
            dataset_slug: Dataset slug in ``owner/dataset`` format.

        Returns:
            ``SourceMetadataSnapshot`` with version and update timestamp.
        """
        from kaggle.api.kaggle_api_extended import KaggleApi

        api = KaggleApi()
        api.authenticate()
        owner_slug, dataset_name = dataset_slug.split("/", maxsplit=1)
        datasets = api.dataset_list(search=dataset_name, user=owner_slug)

        matched = next(
            (ds for ds in datasets if getattr(ds, "ref", "") == dataset_slug),
            None,
        )
        raw_updated = getattr(matched, "lastUpdated", None) if matched else None
        parsed_updated = _parse_utc_datetime(raw_updated)
        version_number = getattr(matched, "currentVersionNumber", None)
        version_str = str(version_number) if version_number is not None else None
        if version_str is None and parsed_updated is not None:
            version_str = parsed_updated.isoformat()

        return SourceMetadataSnapshot(
            source_name=dataset_name,
            dataset_slug=dataset_slug,
            source_version=version_str,
            source_updated_at=parsed_updated,
            title=getattr(matched, "title", None) if matched else None,
            license_name=getattr(matched, "licenseName", None) if matched else None,
        )

    def download_dataset(self, dataset_slug: str, destination_dir: Path) -> Path:
        """Download and unzip a Kaggle dataset to ``destination_dir``.

        Args:
            dataset_slug: Dataset slug in ``owner/dataset`` format.
            destination_dir: Local directory receiving extracted files.

        Returns:
            Path to ``destination_dir``.
        """
        from kaggle.api.kaggle_api_extended import KaggleApi

        destination_dir.mkdir(parents=True, exist_ok=True)
        api = KaggleApi()
        api.authenticate()
        api.dataset_download_files(
            dataset_slug,
            path=str(destination_dir),
            unzip=True,
            quiet=True,
        )
        return destination_dir


def _parse_utc_datetime(raw_value: object) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        if raw_value.tzinfo is None:
            return raw_value.replace(tzinfo=UTC)
        return raw_value.astimezone(UTC)
    if isinstance(raw_value, str) and raw_value.strip():
        normalized = raw_value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return None


def compute_sha256(file_path: Path) -> str:
    """Compute the hex SHA-256 checksum of a file.

    Args:
        file_path: Path to the file to hash.

    Returns:
        Lowercase 64-character hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while chunk := handle.read(_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def has_upstream_changed(
    snapshot: SourceMetadataSnapshot,
    last_version: str | None,
    last_updated_at: datetime | None,
) -> bool:
    """Determine whether upstream metadata indicates a newer dataset version.

    Args:
        snapshot: Current upstream metadata snapshot.
        last_version: ``source_version`` from the latest successful batch.
        last_updated_at: ``source_updated_at`` from the latest successful batch.

    Returns:
        ``True`` if there is no prior batch or metadata differs; ``False`` if both
        version and timestamp match the previous successful load.
    """
    if last_version is None and last_updated_at is None:
        return True
    if (
        snapshot.source_version is not None
        and last_version is not None
        and snapshot.source_version != last_version
    ):
        return True
    if snapshot.source_updated_at is not None and last_updated_at is not None:
        last_utc = (
            last_updated_at.replace(tzinfo=UTC)
            if last_updated_at.tzinfo is None
            else last_updated_at.astimezone(UTC)
        )
        if snapshot.source_updated_at != last_utc:
            return True
    return snapshot.source_version is None and snapshot.source_updated_at is None


def is_checksum_unchanged(checksum: str, last_checksum: str | None) -> bool:
    """Return ``True`` if the downloaded file matches the last loaded checksum.

    Args:
        checksum: SHA-256 hex digest of the newly downloaded file.
        last_checksum: SHA-256 hex digest from the latest successful batch.

    Returns:
        ``True`` when ``last_checksum`` is present and matches ``checksum``.
    """
    return last_checksum is not None and checksum == last_checksum


def _locate_downloaded_file(directory: Path, file_name: str) -> Path:
    direct = directory / file_name
    if direct.is_file():
        return direct
    for zip_path in sorted(directory.glob("*.zip")):
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(directory)
        if direct.is_file():
            return direct
    for candidate in sorted(directory.rglob(file_name)):
        if candidate.is_file():
            shutil.copy2(candidate, direct)
            return direct
    raise FileNotFoundError(
        f"Expected file {file_name!r} was not found in downloaded dataset {directory}"
    )


def fetch_zomato_dataset(
    dataset_slug: str,
    file_name: str,
    target_dir: Path,
    *,
    client: KaggleClientProtocol | None = None,
    last_version: str | None = None,
    last_updated_at: datetime | None = None,
    last_checksum: str | None = None,
    skip_if_unchanged: bool = True,
) -> FetchResult:
    """Check upstream version metadata, download when changed, and verify checksum.

    Args:
        dataset_slug: Kaggle dataset identifier (``owner/dataset``).
        file_name: Expected CSV file name inside the dataset.
        target_dir: Local staging directory for downloads.
        client: Optional Kaggle client implementation for dependency injection.
        last_version: Previously loaded ``source_version``.
        last_updated_at: Previously loaded ``source_updated_at``.
        last_checksum: Previously loaded SHA-256 checksum.
        skip_if_unchanged: Whether to skip loading when version or checksum matches.

    Returns:
        ``FetchResult`` describing either a downloaded file or a skipped run.
    """
    kaggle_client = client if client is not None else DefaultKaggleClient()
    snapshot = kaggle_client.get_dataset_metadata(dataset_slug)

    if skip_if_unchanged and not has_upstream_changed(
        snapshot, last_version, last_updated_at
    ):
        logger.info(
            "Upstream dataset unchanged; skipping download",
            extra={"source_id": snapshot.source_name},
        )
        return FetchResult(
            status=RUN_STATUS_SKIPPED_UNCHANGED,
            snapshot=snapshot,
            local_file_path=None,
            file_checksum=last_checksum,
        )

    downloaded_dir = kaggle_client.download_dataset(dataset_slug, target_dir)
    csv_path = _locate_downloaded_file(downloaded_dir, file_name)
    checksum = compute_sha256(csv_path)

    if skip_if_unchanged and is_checksum_unchanged(checksum, last_checksum):
        logger.info(
            "Downloaded file checksum unchanged; skipping load",
            extra={"source_id": snapshot.source_name},
        )
        return FetchResult(
            status=RUN_STATUS_SKIPPED_UNCHANGED,
            snapshot=snapshot,
            local_file_path=None,
            file_checksum=checksum,
        )

    return FetchResult(
        status="downloaded",
        snapshot=snapshot,
        local_file_path=csv_path,
        file_checksum=checksum,
    )
