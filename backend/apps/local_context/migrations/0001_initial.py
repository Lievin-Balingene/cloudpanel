from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LocalSiteProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("country", models.CharField(default="CD", max_length=8)),
                ("timezone", models.CharField(default="Africa/Kinshasa", max_length=64)),
                ("currency", models.CharField(default="CDF", max_length=8)),
                ("data_saver", models.BooleanField(default=False)),
                ("require_phone", models.BooleanField(default=False)),
                ("phone_prefix", models.CharField(default="+243", max_length=8)),
                ("notify_channel", models.CharField(default="whatsapp", max_length=16)),
                ("backup_window_start", models.PositiveSmallIntegerField(default=1)),
                ("backup_window_end", models.PositiveSmallIntegerField(default=6)),
                ("defer_heavy_jobs", models.BooleanField(default=True)),
                ("payment_instructions", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Profil local"},
        ),
        migrations.CreateModel(
            name="LocalPayment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(max_length=8)),
                (
                    "method",
                    models.CharField(
                        choices=[
                            ("orange_money", "Orange Money"),
                            ("mtn_momo", "MTN MoMo"),
                            ("moov_money", "Moov Money"),
                            ("wave", "Wave"),
                            ("mpesa", "M-Pesa"),
                            ("airtel_money", "Airtel Money"),
                            ("flooz", "Flooz"),
                            ("cash", "Espèces"),
                            ("bank_transfer", "Virement"),
                            ("other", "Autre"),
                        ],
                        max_length=24,
                    ),
                ),
                ("reference", models.CharField(blank=True, default="", max_length=80)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("paid_at", models.DateTimeField()),
                ("covers_until", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "recorded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_local_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="local_payments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-paid_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="localpayment",
            index=models.Index(fields=["user", "-paid_at"], name="local_conte_user_id_paid_idx"),
        ),
        migrations.AddIndex(
            model_name="localpayment",
            index=models.Index(fields=["covers_until"], name="local_conte_covers__idx"),
        ),
    ]
