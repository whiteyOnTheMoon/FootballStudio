"""P0: shared paid-API budget lock and auditable USD reservations.

Additive only. Single gate row pk=1 is inserted here, never lazily at runtime.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def seed_gate(apps, schema_editor):
    Gate = apps.get_model("production", "SharedPaidApiBudgetLock")
    Gate.objects.using(schema_editor.connection.alias).get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0009_bounded_official_research"),
    ]
    operations = [
        migrations.CreateModel(
            name="SharedPaidApiBudgetLock",
            fields=[
                ("id", models.PositiveSmallIntegerField(
                    default=1, editable=False, primary_key=True, serialize=False,
                )),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={"constraints": [
                models.CheckConstraint(
                    condition=models.Q(id=1), name="prod_paid_budget_singleton",
                ),
            ]},
        ),
        migrations.CreateModel(
            name="PaidApiCharge",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name="ID",
                )),
                ("request_key", models.UUIDField(unique=True)),
                ("purpose", models.CharField(
                    max_length=12, choices=[
                        ("llm", "Text generation"),
                        ("tts", "Speech generation"),
                        ("media", "Paid media"),
                        ("research", "Paid research"),
                    ],
                )),
                ("provider", models.CharField(max_length=48)),
                ("rate_key", models.CharField(max_length=120)),
                ("model_id", models.CharField(max_length=100)),
                ("price_version", models.CharField(max_length=60)),
                ("unit_name", models.CharField(max_length=30)),
                ("unit_count", models.PositiveIntegerField()),
                ("quoted_unit_usd", models.DecimalField(
                    max_digits=14, decimal_places=6,
                )),
                ("reserved_usd", models.DecimalField(
                    max_digits=14, decimal_places=6,
                )),
                ("actual_usd", models.DecimalField(
                    max_digits=14, decimal_places=6,
                    null=True, blank=True,
                )),
                ("period_start", models.DateField()),
                ("state", models.CharField(
                    max_length=12, default="reserved", choices=[
                        ("reserved", "Budget reserved; dispatch not confirmed"),
                        ("settled", "Provider cost confirmed"),
                        ("uncertain", "Provider cost unknown; reserve retained"),
                        ("released", "Confirmed no paid request was sent"),
                    ],
                )),
                ("reserved_at", models.DateTimeField(
                    default=django.utils.timezone.now,
                )),
                ("reconciled_at", models.DateTimeField(null=True, blank=True)),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="paid_api_charges", to="production.productionjob",
                )),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["period_start", "state"],
                        name="prod_paid_month_state_ix",
                    ),
                    models.Index(
                        fields=["job", "reserved_at"],
                        name="prod_paid_job_time_ix",
                    ),
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(unit_count__gte=1),
                        name="prod_paid_units_positive",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(quoted_unit_usd__gt=0),
                        name="prod_paid_unit_cost_gt0",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(reserved_usd__gt=0),
                        name="prod_paid_reserve_gt0",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(actual_usd__isnull=True) |
                        models.Q(actual_usd__gte=0),
                        name="prod_paid_actual_nonneg",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(state="settled", actual_usd__isnull=False) |
                        ~models.Q(state="settled"),
                        name="prod_paid_settle_has_cost",
                    ),
                ],
            },
        ),
        migrations.RunPython(seed_gate, migrations.RunPython.noop),
    ]
