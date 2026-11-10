# Generated schema addition for safe on-demand external catalog caching.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clubs", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="league",
            name="catalog_season",
            field=models.CharField(blank=True, max_length=10),
        ),
        migrations.AddField(
            model_name="league",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
