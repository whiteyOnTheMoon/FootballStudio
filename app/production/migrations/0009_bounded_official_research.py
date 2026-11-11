"""Bounded, single-use execution state and unverified page metadata."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0008_official_research_request"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="officialresearchrequest",
            name="production_research_one_pending_job",
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="started_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="finished_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="lease_expires_at",
            field=models.DateTimeField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="lease_key",
            field=models.UUIDField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="failure_code",
            field=models.CharField(max_length=40, blank=True),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="result_count",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="officialresearchrequest", name="result_dossier_version",
            field=models.PositiveIntegerField(null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="officialresearchrequest", name="status",
            field=models.CharField(
                max_length=16, default="pending_worker",
                choices=[
                    ("pending_worker", "Recorded; no worker available"),
                    ("cancelled", "Cancelled by the job owner"),
                    ("expired", "Consent expired without execution"),
                    ("running", "Research in progress"),
                    ("succeeded", "Bounded metadata research completed"),
                    ("failed", "Research stopped without imported pages"),
                    ("blocked", "Research blocked by site or security rules"),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="officialresearchrequest",
            constraint=models.UniqueConstraint(
                fields=("job",),
                condition=models.Q(status__in=("pending_worker", "running")),
                name="prod_res_one_active_job",
            ),
        ),
        migrations.CreateModel(
            name="OfficialResearchPage",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("position", models.PositiveSmallIntegerField()),
                ("url", models.URLField(max_length=750)),
                ("title", models.CharField(max_length=160, blank=True)),
                ("headings", models.JSONField(default=list)),
                ("category", models.CharField(max_length=20, blank=True)),
                ("retrieved_at", models.DateTimeField()),
                ("verification_state", models.CharField(
                    max_length=16, default="unverified", editable=False,
                )),
                ("request", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="pages", to="production.officialresearchrequest",
                )),
                ("saved_source", models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="official_research_page_metadata",
                    to="production.sourcereference", null=True, blank=True,
                )),
            ],
            options={
                "ordering": ("position",),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("request", "position"),
                        name="prod_res_page_position_uq",
                    ),
                    models.UniqueConstraint(
                        fields=("request", "url"), name="prod_res_page_url_uq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(position__gte=0, position__lte=3),
                        name="prod_res_page_four_max",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(verification_state="unverified"),
                        name="prod_res_page_unverified",
                    ),
                ],
            },
        ),
    ]
