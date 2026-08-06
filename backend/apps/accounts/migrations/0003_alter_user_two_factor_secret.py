from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_rename_accounts_us_role_7a0e3a_idx_accounts_us_role_2b136f_idx_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="two_factor_secret",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
    ]
