from career_automation.base import Adapter, Outcome, SubmissionContext, SubmissionResult


class ManualAdapter(Adapter):
    """Fallback for every site we are not permitted / able to automate: hand the job back to the user."""

    name = "manual"

    def can_handle(self, url, allowed_domains):
        return True

    def submit(self, ctx: SubmissionContext) -> SubmissionResult:
        return SubmissionResult(
            Outcome.MANUAL_REQUIRED, "unsupported_site",
            "Automated submission is not available for this employer's site. Apply using the job link with your approved "
            "documents, then mark the application as applied.",
        )
