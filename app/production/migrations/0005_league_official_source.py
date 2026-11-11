"""Add first-class official league provenance without touching existing sources."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0004_manual_market_value"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sourcereference",
            name="source_kind",
            field=models.CharField(
                max_length=16,
                choices=[
                    ("wikidata", "Wikidata"),
                    ("wikipedia", "Wikipedia"),
                    ("club_official", "Official club site"),
                    ("league_official", "Official league site"),
                    ("news", "News"),
                    ("other", "Other"),
                ],
            ),
        ),
    ]
