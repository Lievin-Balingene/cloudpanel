from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_passwordresetchallenge"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="user",
            name="notify_channel",
            field=models.CharField(blank=True, default="whatsapp", max_length=16),
        ),
        migrations.AddField(
            model_name="user",
            name="paid_until",
            field=models.DateField(blank=True, null=True),
        ),
    ]
