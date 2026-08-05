# Generated manually for OpenLiteSpeed web_engine
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("domains", "0002_rename_domains_dom_owner_i_0a1b2c_idx_domains_dom_owner_i_4f2b13_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="web_engine",
            field=models.CharField(
                choices=[("nginx", "Nginx + PHP-FPM"), ("ols", "OpenLiteSpeed")],
                db_index=True,
                default="nginx",
                help_text="Moteur pour PHP/static (Python/Node restent en proxy Nginx).",
                max_length=16,
            ),
        ),
    ]
