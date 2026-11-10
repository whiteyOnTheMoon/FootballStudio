# Support 2-3 letter football association identifiers, incl. SCO/NIR/WAL.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0001_initial"),
        ("clubs", "0003_confederation_offline_coverage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productionjob",
            name="country_code",
            field=models.CharField(max_length=3),
        ),
    ]
