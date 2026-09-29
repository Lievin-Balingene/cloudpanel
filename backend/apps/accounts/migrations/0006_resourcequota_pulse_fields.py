# Generated manually for V-zone Pulse resource fields on ResourceQuota

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_resellerprivileges_max_accounts"),
    ]

    operations = [
        migrations.AddField(
            model_name="resourcequota",
            name="inode_limit",
            field=models.PositiveIntegerField(default=200000),
        ),
        migrations.AddField(
            model_name="resourcequota",
            name="max_processes",
            field=models.PositiveIntegerField(default=100),
        ),
    ]
