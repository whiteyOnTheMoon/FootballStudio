"""Persist job-scoped and versioned research metadata for FS-014b.1."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0002_global_association_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="FactDossier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("version", models.PositiveIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fact_dossiers", to="production.productionjob")),
            ],
        ),
        migrations.CreateModel(
            name="SourceReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("url", models.URLField(max_length=750)),
                ("source_kind", models.CharField(choices=[
                    ("wikidata", "Wikidata"), ("wikipedia", "Wikipedia"),
                    ("club_official", "Official club site"), ("news", "News"),
                    ("other", "Other"),
                ], max_length=16)),
                ("title", models.CharField(blank=True, max_length=250)),
                ("external_id", models.CharField(blank=True, max_length=120)),
                ("retrieved_at", models.DateTimeField()),
                ("access_state", models.CharField(choices=[
                    ("accessible", "Accessible"), ("not_found", "Not found"),
                    ("unavailable", "Unavailable"), ("restricted", "Restricted"),
                    ("error", "Error"),
                ], max_length=16)),
                ("dossier", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sources", to="production.factdossier")),
            ],
        ),
        migrations.CreateModel(
            name="Fact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("predicate", models.CharField(max_length=100)),
                ("value", models.JSONField(blank=True, null=True)),
                ("assertion_text", models.TextField()),
                ("verification_state", models.CharField(choices=[
                    ("unverified", "Unverified"), ("verified", "Verified"),
                    ("conflicted", "Conflicted"), ("insufficient_sources", "Insufficient sources"),
                    ("rejected", "Rejected"),
                ], default="unverified", max_length=24)),
                ("dossier", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="facts", to="production.factdossier")),
            ],
        ),
        migrations.CreateModel(
            name="Evidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("locator", models.CharField(max_length=250)),
                ("summary", models.TextField(blank=True)),
                ("role", models.CharField(choices=[
                    ("supports", "Supports"), ("contradicts", "Contradicts"),
                    ("context_only", "Context only"), ("unknown", "Unknown"),
                ], default="unknown", max_length=16)),
                ("fact", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="evidence", to="production.fact")),
                ("source", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evidence", to="production.sourcereference")),
            ],
        ),
        migrations.AddConstraint(
            model_name="factdossier",
            constraint=models.UniqueConstraint(fields=("job", "version"), name="production_dossier_job_version_uniq"),
        ),
        migrations.AddConstraint(
            model_name="factdossier",
            constraint=models.CheckConstraint(condition=models.Q(version__gte=1), name="production_dossier_positive_version"),
        ),
    ]
