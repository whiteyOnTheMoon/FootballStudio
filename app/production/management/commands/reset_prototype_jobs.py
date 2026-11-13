"""Explicit operator-only removal of prototype test jobs for clean-room runs.

Destructive use requires an *already restored-and-verified* PostgreSQL backup,
plus two separate intent flags. This command cannot verify the operator's
backup attestation; see scripts/verify_postgres_backup.sh. Never call this
command from an HTTP request, web view, startup process, or CI fixture.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app.production.models import (
    Evidence, OfficialResearchRequest, PaidApiCharge, ProductionJob,
)


_CONFIRM = "DELETE_PROTOTYPE_TEST_JOBS"
_MAX_JOB_COUNT = 200


class Command(BaseCommand):
    help = (
        "Dry-run by default; optionally remove ONLY prototype test jobs and "
        "their dependent research snapshots after verifying a DB backup. "
        "Never removes film jobs, users, catalog or paid ledger records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute", action="store_true",
            help="Actually delete prototype jobs; default previews only.",
        )
        parser.add_argument(
            "--confirm", default="",
            help=f"Required with --execute: {_CONFIRM}",
        )
        parser.add_argument(
            "--backup-verified", action="store_true",
            help="Attest that a fresh PostgreSQL archive was restored/verified.",
        )
        parser.add_argument(
            "--owner-id", type=int, default=None,
            help="Optionally scope deletion to the selected job owner's ID.",
        )

    def _queryset(self, owner_id):
        jobs = ProductionJob.objects.filter(
            kind=ProductionJob.Kind.PROTOTYPE,
        )
        return (
            jobs.filter(owner_id=owner_id)
            if owner_id is not None else jobs
        )

    def handle(self, *args, **options):
        owner_id = options["owner_id"]
        if owner_id is not None and owner_id <= 0:
            raise CommandError("--owner-id must be a positive integer.")
        if options["execute"] and (
            options["confirm"] != _CONFIRM
            or options["backup_verified"] is not True
        ):
            raise CommandError(
                "Deletion blocked: first restore-verify a fresh PostgreSQL "
                "backup; then pass --execute --backup-verified "
                f"--confirm={_CONFIRM}. No data was deleted."
            )
        if not options["execute"] and (
            options["confirm"] or options["backup_verified"]
        ):
            raise CommandError(
                "--confirm/--backup-verified require --execute. "
                "No data was deleted."
            )

        qs = self._queryset(owner_id)
        total = qs.count()
        self.stdout.write(
            f"Scope: {'owner '+str(owner_id) if owner_id else 'all owners'}; "
            f"job kind: {ProductionJob.Kind.PROTOTYPE}; "
            f"matching test jobs: {total}."
        )
        for job in qs.order_by("pk")[:20]:
            self.stdout.write(
                f"  #{job.pk} · owner #{job.owner_id} · {job.club_name} "
                f"· status={job.status}"
            )
        if total > 20:
            self.stdout.write(f"  … and {total - 20} more test jobs.")
        if total > _MAX_JOB_COUNT:
            raise CommandError(
                f"Safety limit: {total} test jobs exceed {_MAX_JOB_COUNT}. "
                "No data was deleted."
            )
        blocked_costs = PaidApiCharge.objects.filter(job__in=qs).count()
        running = OfficialResearchRequest.objects.filter(
            job__in=qs, status=OfficialResearchRequest.Status.RUNNING,
        ).count()
        self.stdout.write(
            f"Paid-ledger records linked to these jobs: {blocked_costs}. "
            f"Running official research requests: {running}."
        )
        if blocked_costs or running:
            raise CommandError(
                "Blocked: paid-ledger records or running official research "
                "requests belong to these jobs. Nothing deleted."
            )
        if not options["execute"]:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN ONLY. No data deleted. Existing users, "
                    "countries, leagues, clubs and paid-budget ledger "
                    "are outside the target scope."
                )
            )
            return

        with transaction.atomic():
            # Lock job rows before deleting. Validate again INSIDE the same
            # transaction to prevent a stale dry run from becoming authority.
            ids = list(
                self._queryset(owner_id).select_for_update()
                .order_by("pk").values_list("pk", flat=True)
            )
            if len(ids) != total:
                raise CommandError(
                    "Test-job list changed; deletion rolled back."
                )
            if PaidApiCharge.objects.filter(job_id__in=ids).exists():
                raise CommandError(
                    "Paid-ledger link found; deletion rolled back."
                )
            if OfficialResearchRequest.objects.filter(
                job_id__in=ids,
                status=OfficialResearchRequest.Status.RUNNING,
            ).exists():
                raise CommandError(
                    "Running official-research job found; deletion rolled back."
                )
            # Evidence.source uses PROTECT: remove child evidence before
            # deleting its fact and source in the same dossier cascade.
            evidence_deleted, _ = Evidence.objects.filter(
                fact__dossier__job_id__in=ids,
            ).delete()
            removed, details = ProductionJob.objects.filter(
                pk__in=ids,
                kind=ProductionJob.Kind.PROTOTYPE,
            ).delete()
            if self._queryset(owner_id).exists():
                raise CommandError(
                    "Some prototype jobs remain; deletion rolled back."
                )

        self.stdout.write(self.style.SUCCESS(
            f"Deleted {len(ids)} prototype test job(s), "
            f"{evidence_deleted} evidence link(s), "
            f"{removed} other related database row(s)."
        ))
        self.stdout.write(
            "Preserved: film jobs, users, country/league/club catalog, "
            "paid API budget lock and cost ledger. "
            "Existing job IDs are not reused automatically."
        )
