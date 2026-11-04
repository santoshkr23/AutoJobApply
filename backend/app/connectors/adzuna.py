from collections.abc import Iterable
from datetime import datetime

from app.connectors.base import ConnectorError, DiscoveryQuery, JobConnector, RawJob
from app.core.config import get_settings

SUPPORTED = {"in", "us", "gb", "ca", "au", "de", "fr", "nl", "pl", "sg", "es", "it"}


class AdzunaConnector(JobConnector):
    key = "adzuna"
    display_name = "Adzuna (official API)"
    requires_credentials = True
    terms_url = "https://developer.adzuna.com/"
    terms_note = "Official API; requires app_id/app_key. Descriptions are snippets and links go to the Adzuna redirect URL."

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.adzuna_app_id and s.adzuna_app_key)

    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        s = get_settings()
        if not self.is_configured():
            raise ConnectorError("adzuna: ADZUNA_APP_ID/ADZUNA_APP_KEY not configured")
        countries = [c.lower() for c in (query.countries or self.config.get("countries") or ["in", "us", "gb"]) if c.lower() in SUPPORTED]
        what = " ".join(query.keywords[:3]) or self.config.get("what", "data engineer")
        per_country = max(10, min(50, query.limit // max(len(countries), 1)))
        with self.http() as client:
            for cc in countries:
                data = self.get_json(
                    client,
                    f"https://api.adzuna.com/v1/api/jobs/{cc}/search/1",
                    params={"app_id": s.adzuna_app_id, "app_key": s.adzuna_app_key, "results_per_page": per_country,
                            "what": what, "content-type": "application/json"},
                )
                for j in data.get("results", []):
                    posted = None
                    if j.get("created"):
                        try:
                            posted = datetime.fromisoformat(j["created"].replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    yield RawJob(
                        external_id=str(j["id"]),
                        title=j.get("title", ""),
                        company=(j.get("company") or {}).get("display_name", ""),
                        description=j.get("description", ""),
                        url=j.get("redirect_url", ""),
                        location_text=(j.get("location") or {}).get("display_name"),
                        country=cc.upper(),
                        salary_min=int(j["salary_min"]) if j.get("salary_min") else None,
                        salary_max=int(j["salary_max"]) if j.get("salary_max") else None,
                        salary_period="year" if j.get("salary_min") else None,
                        employment_type=j.get("contract_time") or j.get("contract_type"),
                        posted_at=posted,
                        attribution="via Adzuna",
                    )
