from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("local_context", "0001_initial"),
    ]

    operations = [
        migrations.DeleteModel(name="LocalPayment"),
        migrations.RemoveField(model_name="localsiteprofile", name="currency"),
        migrations.RemoveField(model_name="localsiteprofile", name="payment_instructions"),
        migrations.AddField(
            model_name="localsiteprofile",
            name="lite_panel",
            field=models.BooleanField(default=False),
        ),
    ]
