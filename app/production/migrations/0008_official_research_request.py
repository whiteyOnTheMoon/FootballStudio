"""Record explicit, single-use and expiring research consent; never start a crawler."""
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("production", "0007_source_confirmation"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfficialResearchRequest",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID",
                )),
                ("request_key", models.UUIDField()),
                ("expected_version", models.PositiveIntegerField()),
                ("confirmed_url", models.URLField(max_length=750)),
                ("confirmed_domain", models.CharField(max_length=253)),
                ("context", models.CharField(
                    max_length=8, choices=[("club", "Club"), ("league", "League")],
                )),
                ("domain_rechecked", models.BooleanField(default=False)),
                ("terms_rechecked", models.BooleanField(default=False)),
                ("one_time_approved", models.BooleanField(default=False)),
                ("consented_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("expires_at", models.DateTimeField()),
                ("status", models.CharField(
                    max_length=16, default="pending_worker",
                    choices=[
                        ("pending_worker", "Recorded; no worker available"),
                        ("cancelled", "Cancelled by the job owner"),
                        ("expired", "Consent expired without execution"),
                    ],
                )),
                ("attempt_count", models.PositiveSmallIntegerField(default=0)),
                ("max_pages", models.PositiveSmallIntegerField(default=4)),
                ("cancelled_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="official_research_requests",
                    to="production.productionjob",
                )),
                ("source", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="research_requests",
                    to="production.sourcereference",
                )),
                ("requested_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="football_research_consents",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["requested_by", "confirmed_domain", "consented_at"],
                        name="production_research_owner_host_idx",
                    ),
                    models.Index(
                        fields=["job", "created_at"],
                        name="production_research_job_time_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("job", "request_key"),
                        name="production_research_req_key_uniq",
                    ),
                    models.UniqueConstraint(
                        fields=("job",), condition=models.Q(status="pending_worker"),
                        name="production_research_one_pending_job",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(expected_version__gte=1),
                        name="production_research_positive_version",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(attempt_count__lte=1),
                        name="production_research_max_one_attempt",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(max_pages=4),
                        name="production_research_four_pages",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(expires_at__gt=models.F("consented_at")),
                        name="production_research_positive_ttl",
                    ),
                ],
            },
        ),
    ]
