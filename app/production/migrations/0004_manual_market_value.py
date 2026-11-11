"""Nullable manual squad-value snapshot; existing M1 jobs remain unchanged."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0003_fact_dossier"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionjob",
            name="manual_market_value_amount",
            field=models.DecimalField(
                max_digits=16, decimal_places=2, null=True, blank=True,
            ),
        ),
        migrations.AddField(
            model_name="productionjob",
            name="manual_market_value_currency",
            field=models.CharField(
                max_length=3,
                choices=[
                    ("EUR", "Euro"),
                    ("GBP", "British pound"),
                    ("USD", "US dollar"),
                ],
                default="EUR",
            ),
        ),
        migrations.AddField(
            model_name="productionjob",
            name="manual_market_value_as_of",
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name="productionjob",
            name="manual_market_value_source_url",
            field=models.URLField(max_length=500, blank=True),
        ),
        migrations.AddConstraint(
            model_name="productionjob",
            constraint=models.CheckConstraint(
                condition=models.Q(manual_market_value_amount__isnull=True)
                | models.Q(manual_market_value_amount__gt=0),
                name="production_job_manual_value_positive",
            ),
        ),
    ]
