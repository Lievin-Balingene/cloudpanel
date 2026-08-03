from __future__ import annotations

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DnsZone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(db_index=True, max_length=255, unique=True)),
                ("ttl_default", models.PositiveIntegerField(default=14400)),
                ("soa_primary_ns", models.CharField(default="ns1.vzone.local.", max_length=255)),
                ("soa_admin_email", models.CharField(default="hostmaster.vzone.local.", max_length=255)),
                ("soa_serial", models.PositiveIntegerField(default=1)),
                ("soa_refresh", models.PositiveIntegerField(default=3600)),
                ("soa_retry", models.PositiveIntegerField(default=1800)),
                ("soa_expire", models.PositiveIntegerField(default=1209600)),
                ("soa_minimum", models.PositiveIntegerField(default=86400)),
                ("dnssec_enabled", models.BooleanField(default=False)),
                ("dnssec_algorithm", models.CharField(blank=True, default="", max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dns_zones", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="DnsRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("record_type", models.CharField(choices=[("A", "A"), ("AAAA", "AAAA"), ("CNAME", "CNAME"), ("TXT", "TXT"), ("MX", "MX"), ("SRV", "SRV"), ("CAA", "CAA"), ("NS", "NS")], db_index=True, max_length=8)),
                ("name", models.CharField(help_text="Nom relatif (@ pour apex, www, mail…).", max_length=255)),
                ("content", models.TextField()),
                ("ttl", models.PositiveIntegerField(blank=True, null=True)),
                ("priority", models.PositiveIntegerField(blank=True, null=True)),
                ("weight", models.PositiveIntegerField(blank=True, null=True)),
                ("port", models.PositiveIntegerField(blank=True, null=True)),
                ("flags", models.PositiveIntegerField(blank=True, help_text="CAA flags", null=True)),
                ("tag", models.CharField(blank=True, default="", help_text="CAA tag", max_length=32)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("zone", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="records", to="dns.dnszone")),
            ],
            options={"ordering": ("record_type", "name")},
        ),
        migrations.AddIndex(
            model_name="dnsrecord",
            index=models.Index(fields=["zone", "record_type"], name="dns_dnsreco_zone_id_0a1b2c_idx"),
        ),
    ]
