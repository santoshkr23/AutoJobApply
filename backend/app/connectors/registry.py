from app.connectors.adzuna import AdzunaConnector
from app.connectors.base import JobConnector
from app.connectors.employer_boards import GreenhouseConnector, JsonFeedConnector, LeverConnector
from app.connectors.mock import MockConnector
from app.connectors.remotive import RemotiveConnector
from app.core.config import get_settings

CONNECTORS: dict[str, type[JobConnector]] = {
    c.key: c
    for c in (MockConnector, RemotiveConnector, AdzunaConnector, GreenhouseConnector, LeverConnector, JsonFeedConnector)
}

# Default sources created on first seed. Real sources start disabled until an admin has reviewed their terms.
DEFAULT_SOURCES = [
    {"key": "mock", "name": "Sample jobs (development only)", "connector_type": "mock", "enabled": True, "interval_minutes": 1440, "config": {}},
    {"key": "remotive", "name": "Remotive", "connector_type": "remotive", "enabled": False, "interval_minutes": 720, "config": {"category": "software-dev"}},
    {"key": "adzuna", "name": "Adzuna", "connector_type": "adzuna", "enabled": False, "interval_minutes": 720, "config": {"countries": ["in", "us", "gb", "ca"], "what": "data engineer"}},
]


def build_connector(connector_type: str, config: dict | None = None) -> JobConnector:
    cls = CONNECTORS.get(connector_type)
    if cls is None:
        raise KeyError(f"Unknown connector type '{connector_type}'")
    if connector_type == "mock" and get_settings().is_production_like:
        raise PermissionError("The mock connector is not allowed in staging/production")
    return cls(config)
