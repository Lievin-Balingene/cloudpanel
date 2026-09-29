# Generated manually — max_accounts on ResellerPrivileges

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_resellerprivileges"),
    ]

    operations = [
        migrations.AddField(
            model_name="resellerprivileges",
            name="max_accounts",
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    "Limite de comptes clients pour ce revendeur. "
                    "Null = hériter du package revendeur. 0 = illimité. >0 = plafond."
                ),
                null=True,
            ),
        ),
    ]
