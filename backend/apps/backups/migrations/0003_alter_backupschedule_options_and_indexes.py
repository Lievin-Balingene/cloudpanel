# Generated manually — sync Meta ordering; keep existing index names stable.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("backups", "0002_restic_engine"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="backupschedule",
            options={"ordering": ("owner__username", "frequency")},
        ),
    ]
