from collections.abc import Iterable
from datetime import datetime

from app.connectors.base import DiscoveryQuery, JobConnector, RawJob


class RemotiveConnector(JobConnector):
    key = "remotive"
    display_name = "Remotive (remote jobs)"
    terms_url = "https://remotive.com/api-documentation"
    terms_note = (
        "Public API. Remotive asks for attribution (a link back to the job) and that the API is called sparingly "
        "(a few times per day). Keep the source interval at 6 hours or more."
    )
    URL = "https://remotive.com/api/remote-jobs"

    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        params: dict = {"limit": min(query.limit, 100)}
        category = self.config.get("category")
        if category:
            params["category"] = category
        if query.keywords:
            params["search"] = query.keywords[0]
        with self.http() as client:
            data = self.get_json(client, self.URL, params=params)
        for j in data.get("jobs", []):
            posted = None
            if j.get("publication_date"):
                try:
                    posted = datetime.fromisoformat(j["publication_date"].replace("Z", "+00:00"))
                except ValueError:
                    posted = None
            yield RawJob(
                external_id=str(j["id"]),
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                description=j.get("description", ""),
                url=j.get("url", ""),
                location_text=f"Remote - {j.get('candidate_required_location') or 'Worldwide'}",
                work_mode="remote",
                employment_type=j.get("job_type"),
                posted_at=posted,
                attribution="via Remotive",
            )
