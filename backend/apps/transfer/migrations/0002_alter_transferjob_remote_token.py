# Generated manually for WHM token/password field length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transfer", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transferjob",
            name="remote_token",
            field=models.CharField(blank=True, default="", max_length=4096),
        ),
    ]
