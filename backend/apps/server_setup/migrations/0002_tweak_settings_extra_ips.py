# Generated manually for tweak_settings + extra_ips

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("server_setup", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="serversetup",
            name="tweak_settings",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Tweak Settings WHM (catégories security, email, dns, …).",
            ),
        ),
        migrations.AddField(
            model_name="serversetup",
            name="extra_ips",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Liste d'IP additionnelles du serveur (hors IP publique principale).",
            ),
        ),
    ]
