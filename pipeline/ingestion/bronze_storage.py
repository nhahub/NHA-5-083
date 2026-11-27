"""Append-only Bronze storage backends for local disk and Azure Blob Storage."""

import json
import logging
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

from pipeline.constants import STORAGE_BACKEND_AZURE, STORAGE_BACKEND_LOCAL

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BronzeArtifact:
    """Location and metadata of a persisted Bronze batch artifact."""

    storage_backend: str
    relative_path: str
    uri_or_path: str
    metadata_uri_or_path: str


class BronzeStorage(Protocol):
    """Interface for append-only Bronze batch storage."""

    def write_batch_file(
        self,
        source_name: str,
        batch_date: date,
        batch_id: str,
        local_file_path: Path,
        metadata: Mapping[str, object],
    ) -> BronzeArtifact:
        """Persist a raw source file and ``metadata.json`` without overwriting."""


def build_bronze_relative_dir(
    source_name: str,
    batch_date: date,
    batch_id: str,
) -> Path:
    """Build the canonical ``<source>/<yyyy-mm-dd>/<batch_id>`` path.

    Args:
        source_name: Normalized source identifier (e.g., ``zomato``).
        batch_date: UTC date of ingestion.
        batch_id: Deterministic or UUID batch identifier.

    Returns:
        Relative ``Path`` for the batch folder.
    """
    return Path(source_name) / batch_date.strftime("%Y-%m-%d") / batch_id


class LocalBronzeStorage:
    """Append-only Bronze storage rooted at a local filesystem directory."""

    def __init__(self, base_dir: Path) -> None:
        """Initialize local Bronze storage.

        Args:
            base_dir: Root directory where Bronze batch folders are stored.
        """
        self._base_dir = base_dir

    def write_batch_file(
        self,
        source_name: str,
        batch_date: date,
        batch_id: str,
        local_file_path: Path,
        metadata: Mapping[str, object],
    ) -> BronzeArtifact:
        """Copy raw file and write ``metadata.json`` into a new batch folder.

        Args:
            source_name: Source name (e.g., ``zomato``).
            batch_date: Ingestion UTC date.
            batch_id: Unique batch identifier.
            local_file_path: Path to the downloaded raw file.
            metadata: Batch provenance metadata dictionary.

        Returns:
            ``BronzeArtifact`` pointing to the stored file and metadata.

        Raises:
            FileExistsError: If the target batch file already exists.
        """
        rel_dir = build_bronze_relative_dir(source_name, batch_date, batch_id)
        batch_dir = self._base_dir / rel_dir
        batch_dir.mkdir(parents=True, exist_ok=True)

        target_file = batch_dir / local_file_path.name
        metadata_file = batch_dir / "metadata.json"
        if target_file.exists():
            raise FileExistsError(
                f"Bronze artifact already exists (append-only): {target_file}"
            )

        shutil.copy2(local_file_path, target_file)
        metadata_file.write_text(
            json.dumps(dict(metadata), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        rel_file = (rel_dir / local_file_path.name).as_posix()
        logger.info(
            "Stored local Bronze artifact at %s",
            rel_file,
            extra={"batch_id": batch_id},
        )
        return BronzeArtifact(
            storage_backend=STORAGE_BACKEND_LOCAL,
            relative_path=rel_file,
            uri_or_path=str(target_file),
            metadata_uri_or_path=str(metadata_file),
        )


class AzureBlobBronzeStorage:
    """Append-only Bronze storage backed by an Azure Blob Storage container."""

    def __init__(
        self,
        container_name: str,
        *,
        connection_string: str | None = None,
        account_url: str | None = None,
    ) -> None:
        """Initialize Azure Blob Bronze storage.

        Args:
            container_name: Target Blob container name (e.g., ``bronze``).
            connection_string: Optional Azure Storage connection string.
            account_url: Optional Azure Storage account URL when using MSI/default cred.

        Raises:
            ValueError: If neither ``connection_string`` nor ``account_url`` is given.
        """
        if not connection_string and not account_url:
            raise ValueError(
                "AzureBlobBronzeStorage requires connection_string or account_url"
            )
        self._container_name = container_name
        self._connection_string = connection_string
        self._account_url = account_url

    def _get_container_client(self) -> object:
        from azure.storage.blob import BlobServiceClient

        if self._connection_string:
            service = BlobServiceClient.from_connection_string(self._connection_string)
        else:
            service = BlobServiceClient(account_url=str(self._account_url))
        container_client = service.get_container_client(self._container_name)
        if not container_client.exists():
            container_client.create_container()
        return container_client

    def write_batch_file(
        self,
        source_name: str,
        batch_date: date,
        batch_id: str,
        local_file_path: Path,
        metadata: Mapping[str, object],
    ) -> BronzeArtifact:
        """Upload raw file and ``metadata.json`` to Azure Blob with ``overwrite=False``.

        Args:
            source_name: Source name (e.g., ``zomato``).
            batch_date: Ingestion UTC date.
            batch_id: Unique batch identifier.
            local_file_path: Local path to raw source file.
            metadata: Batch provenance metadata dictionary.

        Returns:
            ``BronzeArtifact`` describing the uploaded blob paths.
        """
        from azure.storage.blob import ContainerClient

        rel_dir = build_bronze_relative_dir(source_name, batch_date, batch_id)
        data_blob_name = f"{rel_dir.as_posix()}/{local_file_path.name}"
        meta_blob_name = f"{rel_dir.as_posix()}/metadata.json"

        raw_client = self._get_container_client()
        if not isinstance(raw_client, ContainerClient):
            raise TypeError("Unexpected Azure container client type")

        with local_file_path.open("rb") as handle:
            raw_client.upload_blob(name=data_blob_name, data=handle, overwrite=False)

        meta_bytes = (json.dumps(dict(metadata), indent=2, default=str) + "\n").encode(
            "utf-8"
        )
        raw_client.upload_blob(name=meta_blob_name, data=meta_bytes, overwrite=False)
        logger.info(
            "Uploaded Bronze blob %s/%s",
            self._container_name,
            data_blob_name,
            extra={"batch_id": batch_id},
        )
        return BronzeArtifact(
            storage_backend=STORAGE_BACKEND_AZURE,
            relative_path=data_blob_name,
            uri_or_path=f"{self._container_name}/{data_blob_name}",
            metadata_uri_or_path=f"{self._container_name}/{meta_blob_name}",
        )


def build_bronze_storage(
    backend: str,
    *,
    local_path: Path,
    container_name: str,
    connection_string: str | None = None,
    account_url: str | None = None,
) -> BronzeStorage:
    """Instantiate the configured Bronze storage backend.

    Args:
        backend: Storage backend identifier (``local`` or ``azure``).
        local_path: Root local directory when ``backend == 'local'``.
        container_name: Azure container name when ``backend == 'azure'``.
        connection_string: Azure Storage connection string if applicable.
        account_url: Azure Storage account URL if applicable.

    Returns:
        Concrete ``BronzeStorage`` implementation.

    Raises:
        ValueError: If ``backend`` is unsupported.
    """
    normalized = backend.strip().lower()
    if normalized == STORAGE_BACKEND_LOCAL:
        return LocalBronzeStorage(local_path)
    if normalized == STORAGE_BACKEND_AZURE:
        return AzureBlobBronzeStorage(
            container_name=container_name,
            connection_string=connection_string,
            account_url=account_url,
        )
    raise ValueError(f"Unsupported storage backend: {backend!r}")
