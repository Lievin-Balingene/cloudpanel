from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ResourceSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("collected_at", models.DateTimeField(db_index=True)),
                ("cpu_percent", models.FloatField()),
                ("ram_percent", models.FloatField()),
                ("ram_used", models.BigIntegerField()),
                ("ram_total", models.BigIntegerField()),
                ("disk_percent", models.FloatField()),
                ("disk_used", models.BigIntegerField()),
                ("disk_total", models.BigIntegerField()),
                ("load_1", models.FloatField(blank=True, null=True)),
                ("load_5", models.FloatField(blank=True, null=True)),
                ("load_15", models.FloatField(blank=True, null=True)),
                ("net_bytes_sent", models.BigIntegerField(default=0)),
                ("net_bytes_recv", models.BigIntegerField(default=0)),
                ("temperatures", models.JSONField(blank=True, default=dict)),
                ("process_count", models.PositiveIntegerField(default=0)),
            ],
            options={"ordering": ("-collected_at",)},
        ),
        migrations.AddIndex(
            model_name="resourcesnapshot",
            index=models.Index(fields=["-collected_at"], name="dashboard_r_collect_0a1b2c_idx"),
        ),
    ]
