"""Track explicit human fact decisions separately from source access/evidence."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("production", "0005_league_official_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="FactReview",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name="ID",
                )),
                ("decision", models.CharField(
                    max_length=24,
                    choices=[
                        ("verified", "Verified"),
                        ("conflicted", "Conflicted"),
                        ("insufficient_sources", "Insufficient sources"),
                        ("rejected", "Rejected"),
                    ],
                )),
                ("note", models.CharField(max_length=500)),
                ("checked_source", models.BooleanField(default=False)),
                ("checked_season", models.BooleanField(default=False)),
                ("reviewed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("fact", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="review", to="production.fact",
                )),
                ("reviewer", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="football_fact_reviews", to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
    ]
