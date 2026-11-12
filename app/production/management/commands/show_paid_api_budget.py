"""Read-only operator report: shared paid API budget, never call a provider."""
from django.core.management.base import BaseCommand
from app.production.paid_api_budget import paid_api_budget_status


class Command(BaseCommand):
    help = "Show global UTC-month paid API budget without secrets or external calls."

    def handle(self, *args, **options):
        status = paid_api_budget_status()
        cap = status["limit_usd"]
        self.stdout.write(f"UTC month: {status['utc_month']}")
        self.stdout.write(
            "Paid API calls: " + ("enabled" if status["enabled"] else "DISABLED")
        )
        self.stdout.write(
            f"Shared monthly USD cap: {cap if cap is not None else 'UNCONFIGURED'}"
        )
        self.stdout.write(
            f"Committed USD (settled + pessimistic open holds): "
            f"{status['committed_usd']}"
        )
        self.stdout.write(
            f"Available USD: "
            f"{status['available_usd'] if cap is not None else 'UNCONFIGURED'}"
        )
        self.stdout.write(
            f"Open/uncertain reservations: {status['open_or_uncertain']}"
        )
        if status["warning_80_percent"]:
            self.stdout.write(
                self.style.WARNING(
                    "WARNING: 80% or more of the UTC monthly API budget is committed."
                )
            )
        if not status["enabled"] or cap is None:
            self.stdout.write(
                "No paid call is authorized by this report. "
                "No provider or network request was made."
            )
