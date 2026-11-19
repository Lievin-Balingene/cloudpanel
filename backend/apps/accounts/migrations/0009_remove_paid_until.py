from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_user_phone_paid_until"),
    ]

    operations = [
        migrations.RemoveField(model_name="user", name="paid_until"),
    ]
