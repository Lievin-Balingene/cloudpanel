# Generated manually for V-zone Cron Jobs
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CronJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "common",
                    models.CharField(
                        choices=[
                            ("custom", "Custom (défini ci‑dessous)"),
                            ("once_per_minute", "Une fois par minute (* * * * *)"),
                            ("once_per_five", "Toutes les 5 minutes (*/5 * * * *)"),
                            ("twice_per_hour", "Deux fois par heure (0,30 * * * *)"),
                            ("once_per_hour", "Une fois par heure (0 * * * *)"),
                            ("twice_per_day", "Deux fois par jour (0 0,12 * * *)"),
                            ("once_per_day", "Une fois par jour (0 0 * * *)"),
                            ("once_per_week", "Une fois par semaine (0 0 * * 0)"),
                            ("once_per_month", "Une fois par mois (0 0 1 * *)"),
                            ("once_per_year", "Une fois par an (0 0 1 1 *)"),
                        ],
                        default="custom",
                        max_length=32,
                    ),
                ),
                ("minute", models.CharField(default="0", max_length=64)),
                ("hour", models.CharField(default="*", max_length=64)),
                ("day", models.CharField(default="*", max_length=64)),
                ("month", models.CharField(default="*", max_length=64)),
                ("weekday", models.CharField(default="*", max_length=64)),
                ("command", models.TextField()),
                (
                    "email_to",
                    models.EmailField(
                        blank=True,
                        default="",
                        help_text="MAILTO — recevoir la sortie de la commande (optionnel).",
                        max_length=254,
                    ),
                ),
                ("label", models.CharField(blank=True, default="", max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cron_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("owner_id", "id"),
            },
        ),
        migrations.AddIndex(
            model_name="cronjob",
            index=models.Index(fields=["owner", "is_active"], name="cron_cronjo_owner_i_7a1b2c_idx"),
        ),
    ]
