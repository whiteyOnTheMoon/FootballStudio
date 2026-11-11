"""Audit manually checked club/league source identity and access separately."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("production", "0006_fact_review"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourceConfirmation",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID",
                )),
                ("checked_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("confirmed_domain", models.CharField(max_length=253)),
                ("identity_confirmed", models.BooleanField(default=False)),
                ("terms_confirmed", models.BooleanField(default=False)),
                ("access_confirmed", models.BooleanField(default=False)),
                ("basis", models.CharField(max_length=300)),
                ("reviewer", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="football_source_confirmations",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("source", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="manual_confirmation",
                    to="production.sourcereference",
                )),
            ],
        ),
    ]
