"""Public employer job-board APIs (Greenhouse, Lever) and a generic authorized JSON feed.

These are the employers' own published job feeds. Configure the company board tokens in the source config.
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from app.connectors.base import ConnectorError, DiscoveryQuery, JobConnector, RawJob


class GreenhouseConnector(JobConnector):
    key = "greenhouse"
    display_name = "Greenhouse public job boards"
    terms_url = "https://developers.greenhouse.io/job-board.html"
    terms_note = "Public Job Board API (read-only). Config: {\"boards\": [\"company-token\", ...]}."

    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        boards = self.config.get("boards") or []
        if not boards:
            raise ConnectorError("greenhouse: no boards configured")
        with self.http() as client:
            for board in boards:
                data = self.get_json(client, f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"})
                for j in data.get("jobs", []):
                    posted = None
                    if j.get("updated_at"):
                        try:
                            posted = datetime.fromisoformat(j["updated_at"].replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    yield RawJob(
                        external_id=f"{board}-{j['id']}",
                        title=j.get("title", ""),
                        company=self.config.get("company_names", {}).get(board, board.replace("-", " ").title()),
                        description=j.get("content", ""),
                        url=j.get("absolute_url", ""),
                        location_text=(j.get("location") or {}).get("name"),
                        posted_at=posted,
                        attribution=f"{board} careers",
                    )


class LeverConnector(JobConnector):
    key = "lever"
    display_name = "Lever public postings"
    terms_url = "https://github.com/lever/postings-api"
    terms_note = "Public Postings API (read-only). Config: {\"companies\": [\"company-slug\", ...]}."

    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        companies = self.config.get("companies") or []
        if not companies:
            raise ConnectorError("lever: no companies configured")
        with self.http() as client:
            for slug in companies:
                data = self.get_json(client, f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
                for j in data if isinstance(data, list) else []:
                    cats = j.get("categories") or {}
                    posted = None
                    if j.get("createdAt"):
                        posted = datetime.fromtimestamp(j["createdAt"] / 1000, tz=UTC)
                    yield RawJob(
                        external_id=f"{slug}-{j['id']}",
                        title=j.get("text", ""),
                        company=self.config.get("company_names", {}).get(slug, slug.replace("-", " ").title()),
                        description=j.get("descriptionPlain") or j.get("description", ""),
                        url=j.get("hostedUrl", ""),
                        apply_url=j.get("applyUrl"),
                        location_text=cats.get("location"),
                        employment_type=cats.get("commitment"),
                        work_mode=(j.get("workplaceType") or "").lower() or None,
                        posted_at=posted,
                        attribution=f"{slug} careers",
                    )


def _dig(obj, path: str):
    for part in path.split("."):
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


class JsonFeedConnector(JobConnector):
    key = "jsonfeed"
    display_name = "Authorized JSON feed"
    terms_note = (
        "Generic connector for a partner/employer feed you are authorized to use. Config: "
        "{\"url\": ..., \"items_path\": \"jobs\", \"mapping\": {\"external_id\": \"id\", \"title\": \"title\", ...}}."
    )

    def fetch(self, query: DiscoveryQuery) -> Iterable[RawJob]:
        url = self.config.get("url")
        mapping = self.config.get("mapping") or {}
        if not url or not mapping:
            raise ConnectorError("jsonfeed: url and mapping are required")
        with self.http() as client:
            data = self.get_json(client, url)
        items = _dig(data, self.config["items_path"]) if self.config.get("items_path") else data
        if not isinstance(items, list):
            raise ConnectorError("jsonfeed: items_path did not resolve to a list")
        for item in items:
            def f(name: str, item=item):
                path = mapping.get(name)
                return _dig(item, path) if path else None

            posted = None
            if f("posted_at"):
                try:
                    posted = datetime.fromisoformat(str(f("posted_at")).replace("Z", "+00:00"))
                except ValueError:
                    pass
            yield RawJob(
                external_id=str(f("external_id") or ""),
                title=str(f("title") or ""),
                company=str(f("company") or self.config.get("default_company", "")),
                description=str(f("description") or ""),
                url=str(f("url") or ""),
                location_text=f("location"),
                employment_type=f("employment_type"),
                posted_at=posted,
                attribution=self.config.get("attribution"),
            )
