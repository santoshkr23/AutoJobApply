"""Connector architecture for job sources.

Only use sources whose terms permit the intended use: official APIs, authorized feeds, public employer
board APIs and partner integrations. Connectors must NOT scrape sites that forbid it. Each connector
declares its terms URL/notes so admins can review them before enabling a source.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from app.core.config import get_settings


@dataclass
class DiscoveryQuery:
    keywords: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    limit: int = 100


@dataclass
class RawJob:
    external_id: str
    title: str
    company: str
    description: str  # may contain HTML; normalized later
    url: str
    location_text: str | None = None
    country: str | None = None
    work_mode: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    salary_period: str | None = None
    employment_type: str | None = None
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    apply_url: str | None = None
    attribution: str | None = None
    is_sample: bool = False


class ConnectorError(Exception):
    pass


class JobConnector(ABC):
    key: str = ""
    display_name: str = ""
    requires_credentials: bool = False
    terms_url: str = ""
    terms_note: str = ""

    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        """Yield jobs. Raise ConnectorError for failures the monitor should record."""

    # Shared HTTP client: identifies the application, short timeouts, no redirects to other schemes.
    def http(self) -> httpx.Client:
        s = get_settings()
        return httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": f"{s.brand_name.replace(' ', '')}/1.0 (job discovery; {s.brand_support_email})"},
        )

    def get_json(self, client: httpx.Client, url: str, **kwargs):
        try:
            r = client.get(url, **kwargs)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            raise ConnectorError(f"{self.key}: HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ConnectorError(f"{self.key}: request failed ({type(exc).__name__})") from exc
