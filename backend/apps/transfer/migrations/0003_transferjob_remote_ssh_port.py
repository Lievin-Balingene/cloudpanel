# Generated manually — SSH port for cpmove SCP download

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transfer", "0002_alter_transferjob_remote_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="transferjob",
            name="remote_ssh_port",
            field=models.PositiveIntegerField(default=22),
        ),
    ]
