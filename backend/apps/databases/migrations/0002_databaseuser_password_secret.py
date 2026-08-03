# Generated manually for phpMyAdmin SSO

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("databases", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="databaseuser",
            name="password_secret",
            field=models.TextField(blank=True, default=""),
        ),
    ]
