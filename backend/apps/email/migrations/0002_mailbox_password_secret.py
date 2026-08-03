# Generated manually for Roundcube SSO

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("email", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailbox",
            name="password_secret",
            field=models.TextField(blank=True, default=""),
        ),
    ]
