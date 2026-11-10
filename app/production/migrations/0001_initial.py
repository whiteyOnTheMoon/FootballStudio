# Initial production/test job model for FS-010b.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clubs", "0002_league_catalog_cache"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductionJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=180)),
                ("language", models.CharField(default="en", max_length=8)),
                ("kind", models.CharField(choices=[("prototype", "M1 selection test"), ("film", "Film production")], default="prototype", max_length=16)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="draft", max_length=16)),
                ("country_code", models.CharField(max_length=2)),
                ("league_name", models.CharField(max_length=160)),
                ("club_name", models.CharField(max_length=160)),
                ("output_path", models.CharField(blank=True, max_length=500)),
                ("error_message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("club", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_jobs", to="clubs.club")),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="production_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-pk")},
        ),
    ]
