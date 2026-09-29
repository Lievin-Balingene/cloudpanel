from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domains", "0003_domain_web_engine"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="force_https",
            field=models.BooleanField(default=True),
        ),
    ]
