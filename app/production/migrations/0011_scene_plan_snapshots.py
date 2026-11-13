"""FS-016c: additive private PostgreSQL JSON scene plan snapshots."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0010_paid_api_shared_budget"),
    ]
    operations = [
        migrations.CreateModel(
            name="ScenePlanSnapshot",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID",
                )),
                ("dossier_version", models.PositiveIntegerField()),
                ("words_per_minute", models.PositiveSmallIntegerField()),
                ("source_script_fingerprint_sha256", models.CharField(max_length=64)),
                ("plan_fingerprint_sha256", models.CharField(max_length=64)),
                ("plan_payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="scene_plan_snapshots", to="production.productionjob",
                )),
            ],
            options={
                "ordering": ("dossier_version", "words_per_minute", "pk"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("job", "dossier_version", "words_per_minute"),
                        name="prod_scene_job_ver_wpm_uq",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(dossier_version__gte=1),
                        name="prod_scene_version_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            words_per_minute__gte=100, words_per_minute__lte=200,
                        ),
                        name="prod_scene_wpm_100_200",
                    ),
                ],
            },
        ),
    ]
