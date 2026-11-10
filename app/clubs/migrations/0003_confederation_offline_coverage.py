# Generated for global confederation catalog and offline snapshot metadata.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("clubs", "0002_league_catalog_cache"),
    ]

    operations = [
        migrations.CreateModel(
            name="Confederation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=10, unique=True)),
                ("name", models.CharField(max_length=120)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.AlterField(
            model_name="country",
            name="code",
            field=models.CharField(max_length=3, unique=True),
        ),
        migrations.AddField(
            model_name="country",
            name="confederation",
            field=models.ForeignKey(
                to="clubs.confederation", null=True, blank=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="associations",
            ),
        ),
        migrations.AddField(
            model_name="league",
            name="coverage_status",
            field=models.CharField(max_length=16, default="reference"),
        ),
        migrations.AddField(
            model_name="league",
            name="source_url",
            field=models.URLField(blank=True, max_length=500),
        ),
    ]
