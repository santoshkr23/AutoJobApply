from career_automation.adapters.form import GenericFormAdapter
from career_automation.adapters.manual import ManualAdapter
from career_automation.base import Adapter


def pick_adapter(url: str, allowed_domains: list[str]) -> Adapter:
    form = GenericFormAdapter()
    return form if form.can_handle(url, allowed_domains) else ManualAdapter()
