"""Service layer for metadata, analytics, and destination profiles."""

from __future__ import annotations

from web.backend.exceptions import NotFoundError
from web.backend.repositories.meta_repository import MetaRepository
from web.backend.schemas.meta import (
    AnalyticsSummaryOut,
    CitiesMetaOut,
    CountriesMetaOut,
    CuisinesMetaOut,
    DestinationProfileOut,
)


class MetaService:
    """Service providing filter metadata, analytics, and destination profiles."""

    def __init__(self, repository: MetaRepository) -> None:
        """Initialize MetaService with a MetaRepository."""
        self._repository = repository

    def list_countries(self) -> CountriesMetaOut:
        """Return available countries with restaurant counts."""
        return CountriesMetaOut(items=self._repository.get_countries())

    def list_cities(self, country: str | None = None) -> CitiesMetaOut:
        """Return available cities optionally filtered by country."""
        clean_country = country.strip() if country and country.strip() else None
        return CitiesMetaOut(items=self._repository.get_cities(country=clean_country))

    def list_cuisines(self) -> CuisinesMetaOut:
        """Return canonical cuisines with groups and counts."""
        return CuisinesMetaOut(items=self._repository.get_cuisines())

    def get_analytics(self, country: str | None = None) -> AnalyticsSummaryOut:
        """Return aggregated dataset analytics."""
        clean_country = country.strip() if country and country.strip() else None
        return self._repository.get_analytics(country=clean_country)

    def get_destination_profile(self, country: str) -> DestinationProfileOut:
        """Return destination profile or raise NotFoundError if unknown country."""
        profile = self._repository.get_destination_profile(country)
        if profile is None:
            raise NotFoundError(f"Destination '{country}' was not found")
        return profile
