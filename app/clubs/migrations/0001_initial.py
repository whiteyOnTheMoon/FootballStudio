# Country/league/club schema for flexible selection; no fixture of fixed clubs.
import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Country",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=2, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="League",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("tier", models.PositiveSmallIntegerField(default=1)),
                ("provider", models.CharField(default="manual", max_length=60)),
                ("provider_id", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("country", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="leagues", to="clubs.country")),
            ],
            options={"ordering": ("country__name", "tier", "name")},
        ),
        migrations.CreateModel(
            name="Club",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160)),
                ("provider", models.CharField(default="manual", max_length=60)),
                ("provider_id", models.CharField(blank=True, max_length=120)),
                ("is_manual", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("league", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="clubs", to="clubs.league")),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.AddConstraint(
            model_name="league",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("country"),
                name="clubs_league_name_country_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="club",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("name"),
                models.F("league"),
                name="clubs_club_name_league_ci",
            ),
        ),
    ]
