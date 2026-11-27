from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("panel_api", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="apitoken",
            name="suspended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
